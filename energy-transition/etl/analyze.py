"""data/*.csv → sql/*.sql (분석 질문 하나에 쿼리 하나) → docs/index.html

    python -m etl.analyze

쿼리 결과를 JSON 으로 화면 틀(etl/dashboard.html)에 넣어 서버 없는 정적 페이지 하나로 만듭니다.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .sources import COUNTRIES, EMBER_GROUP, GROUPS

ROOT = Path(__file__).resolve().parent.parent
QUERIES = ["mix_yearly", "coal_change", "solar_growth", "solar_seasonal", "mix_monthly", "intensity_monthly", "scatter_yearly"]


def _jsonable(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10]
    if isinstance(v, float):
        return round(v, 3)
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return v


def connect(data: Path):
    import duckdb
    con = duckdb.connect()
    con.execute(f"create table ember as select * from read_csv('{data / 'ember_monthly.csv'}', header = true, "
                "columns = {'area': 'varchar', 'month': 'date', 'source': 'varchar', 'generation_twh': 'double', "
                "'share_pct': 'double', 'intensity_g_per_kwh': 'double'})")
    con.execute(f"create table owid as select * from read_csv('{data / 'owid_yearly.csv'}', header = true, auto_detect = true)")
    con.execute("create table grp(source varchar, grp varchar)")
    con.executemany("insert into grp values (?, ?)", list(EMBER_GROUP.items()))
    return con


def run_queries(data: Path = ROOT / "data", sql_dir: Path = ROOT / "sql") -> dict:
    con = connect(data)
    to_ko = {}
    for ko, (ember, owid) in COUNTRIES.items():
        to_ko[ember] = ko
        to_ko[owid] = ko
    out = {}
    try:
        for name in QUERIES:
            cur = con.execute((sql_dir / f"{name}.sql").read_text(encoding="utf-8"))
            cols = [d[0] for d in cur.description]
            rows = []
            for r in cur.fetchall():
                rec = {c: _jsonable(v) for c, v in zip(cols, r)}
                for key in ("country", "area"):
                    if key in rec:
                        rec[key] = to_ko.get(rec[key], rec[key])
                rows.append(rec)
            out[name] = rows
        out["meta"] = {
            "ember_last_month": _jsonable(con.execute("select max(month) from ember where area = 'South Korea'").fetchone()[0]),
            "owid_last_year": con.execute("select max(year) from owid where coal_share_elec is not null").fetchone()[0],
            "countries": list(COUNTRIES), "groups": GROUPS,
        }
    finally:
        con.close()
    return out


def build(out: Path = ROOT / "docs" / "index.html", data: Path = ROOT / "data") -> Path:
    d = run_queries(data)
    d["meta"]["generated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    tpl = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")
    html = tpl.replace("__DATA__", json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    print(build())
