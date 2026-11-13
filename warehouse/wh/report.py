"""dbt 산출물과 웨어하우스 표로 대시보드(docs/index.html)를 만듭니다.

자료는 한 번에 JSON 으로 뽑아 화면 틀(wh/dashboard.html)에 넣습니다 — 서버 없이 정적 페이지 하나로 열립니다.
탭: 개요 · 시세·환율 · 채용 · 전력 · 지진 · 품질(계보·테스트·실행 기록)
"""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import re

LAYER = {"staging": 0, "intermediate": 1, "marts": 2, "snapshot": 2}
COLOR = {"staging": "#5b6cff", "intermediate": "#16a34a", "marts": "#ea7a0c", "snapshot": "#c0338a", "source": "#6b7280", "seed": "#0e9aa7"}
VAR_CSV = re.compile(r'var\("(\w+_csv)"\)')


def lineage(manifest: dict) -> tuple[list[dict], list[tuple[str, str]]]:
    """모델·변경 이력 노드와 (부모, 자식) 간선. 원본 CSV 는 staging 모델의 var() 이름으로 붙입니다."""
    nodes, edges = {}, []
    for uid, n in manifest["nodes"].items():
        if n["resource_type"] not in ("model", "snapshot", "seed"):
            continue
        kind = n["resource_type"] if n["resource_type"] in ("snapshot", "seed") else (n.get("fqn") or ["", "marts"])[1]
        nodes[uid] = {"id": uid, "name": n["name"], "kind": kind, "layer": 0 if kind == "seed" else 1 + LAYER.get(kind, 2),
                      "materialized": n["config"].get("materialized", ""), "description": n.get("description", "")}
    for uid, n in manifest["nodes"].items():
        if uid not in nodes:
            continue
        for parent in n["depends_on"].get("nodes", []):
            if parent in nodes:
                edges.append((parent, uid))
        raw = n.get("raw_code", "")
        for var in VAR_CSV.findall(raw):
            if True:
                sid = "source." + var
                nodes.setdefault(sid, {"id": sid, "name": var.replace("_csv", ".csv"), "kind": "source", "layer": 0,
                                       "materialized": "file", "description": ""})
                edges.append((sid, uid))
    # 집계 표가 변경 이력보다 오른쪽에 오도록, 부모보다 항상 한 칸 이상 오른쪽으로
    changed = True
    while changed:
        changed = False
        for a, b in edges:
            if nodes[b]["layer"] <= nodes[a]["layer"]:
                nodes[b]["layer"] = nodes[a]["layer"] + 1
                changed = True
    return sorted(nodes.values(), key=lambda x: (x["layer"], x["name"])), edges


def _svg(nodes, edges) -> str:
    cols = {}
    for n in nodes:
        cols.setdefault(n["layer"], []).append(n)
    W, BW, BH, GY = 250, 190, 40, 18
    height = max(len(v) for v in cols.values()) * (BH + GY) + 20
    pos = {}
    for layer, items in cols.items():
        y0 = (height - len(items) * (BH + GY) + GY) / 2
        for i, n in enumerate(items):
            pos[n["id"]] = (20 + layer * W, y0 + i * (BH + GY))
    width = 20 + (max(cols) + 1) * W - (W - BW) + 20
    out = [f'<svg viewBox="0 0 {width} {height:.0f}" role="img" aria-label="데이터 계보" style="width:100%;height:auto;min-width:860px">']
    for a, b in edges:
        (x1, y1), (x2, y2) = pos[a], pos[b]
        x1 += BW
        y1 += BH / 2
        y2 += BH / 2
        mx = (x1 + x2) / 2
        out.append(f'<path d="M{x1},{y1:.1f} C{mx},{y1:.1f} {mx},{y2:.1f} {x2},{y2:.1f}" fill="none" stroke="var(--line2)" stroke-width="1.5"/>')
    for n in nodes:
        x, y = pos[n["id"]]
        c = COLOR.get(n["kind"], "#888")
        out.append(f'<g><title>{html.escape(n["description"] or n["name"])}</title>'
                   f'<rect x="{x}" y="{y:.1f}" width="{BW}" height="{BH}" rx="10" fill="var(--card)" stroke="{c}" stroke-width="1.6"/>'
                   f'<rect x="{x}" y="{y:.1f}" width="6" height="{BH}" rx="3" fill="{c}"/>'
                   f'<text x="{x + 16}" y="{y + 18:.1f}" font-size="13" font-weight="700" fill="var(--text)">{html.escape(n["name"])}</text>'
                   f'<text x="{x + 16}" y="{y + 32:.1f}" font-size="10.5" fill="var(--muted)">{n["kind"]} · {n["materialized"]}</text></g>')
    out.append("</svg>")
    return "".join(out)


def _rows(con, sql):
    return [list(r) for r in con.execute(sql).fetchall()]


def collect_data(db: Path) -> dict:
    """화면에 쓸 값을 표에서 뽑습니다. 표가 없으면 그 부분은 비워 둡니다 (일부만 있는 DB 에서도 화면이 열리도록)."""
    if not db.exists():
        return {}
    import duckdb
    con = duckdb.connect(str(db), read_only=True)
    d = {}

    def part(name, fn):
        try:
            d[name] = fn()
        except Exception:
            d[name] = None
    iso = lambda v: v.isoformat() if hasattr(v, "isoformat") else v
    R = lambda sql: [[iso(x) for x in r] for r in con.execute(sql).fetchall()]
    try:
        part("premium", lambda: {a: R(f"""select day_utc, premium_pct, upbit_close_krw, coinbase_close_krw, usdkrw, is_fx_filled
                                          from fct_krw_premium_daily where asset = '{a}' order by 1""")
                                 for (a,) in con.execute("select asset from dim_asset order by 1").fetchall()})
        part("premium_monthly", lambda: R("select month, asset, days, avg_premium_pct, min_premium_pct, max_premium_pct, days_over_3pct, days_negative from fct_premium_monthly order by 1 desc, 2"))
        part("fx", lambda: R("select fx_day, rate from stg_fx where quote = 'KRW' order by 1"))
        part("skills", lambda: R("""
            with recent as (select * from int_job_skills where posted_date >= (select max(posted_date) from int_job_skills) - 27),
                 base as (select count(distinct job_key) n from recent)
            select r.skill, d.category, count(distinct r.job_key), round(100.0 * count(distinct r.job_key) / (select n from base), 1)
            from recent r join dim_skill d using (skill) group by 1, 2 order by 3 desc, 1"""))
        part("jobs_daily", lambda: R("""select posted_date, sum(postings) filter (where source = 'arbeitnow'), sum(postings) filter (where source = 'remoteok'),
                                               sum(tech_postings) from fct_jobs_daily where posted_date >= (select max(posted_date) from fct_jobs_daily) - 44 group by 1 order by 1"""))
        part("jobs_total", lambda: R("""select count(*), count(*) filter (where is_tech), count(*) filter (where is_remote), min(posted_date), max(posted_date),
                                               count(*) filter (where salary_quality = 'annual'), count(*) filter (where salary_quality like 'suspect%'),
                                               median(salary_mid_usd) from fct_job_postings""")[0])
        part("jobs_feed", lambda: R("select source, max(run_date), sum(new_jobs), sum((overlap = 'no' or overlap like 'error%')::int) from stg_jobs_fetch_log group by 1 order by 1"))
        part("demand_daily", lambda: R("select demand_date, peak_mw, mean_mw, min_mw, is_weekend, temp_mean from fct_demand_daily order by 1"))
        part("demand_heat", lambda: R("select month(demand_date), hour_ending, round(avg(demand_mw)) from fct_demand_hourly group by 1, 2 order by 1, 2"))
        part("demand_season", lambda: R("select season, is_weekend, round(avg(peak_mw)), round(avg(load_factor), 3), count(*) from fct_demand_daily group by 1, 2 order by 1, 2"))
        part("quakes_monthly", lambda: R("select month_kst, sum(quakes), max(max_mag) from fct_quakes_monthly where month_kst >= date '2023-11-01' group by 1 order by 1"))
        part("quake_regions", lambda: R("select region, quakes, last_seen_utc::date from dim_region order by 2 desc limit 8"))
        part("quake_total", lambda: R("select count(*), max(mag), max(occurred_at_utc)::date, (select count(*) from snap_quakes), (select count(*) from snap_quakes where dbt_valid_to is not null) from stg_quakes")[0])
    finally:
        con.close()
    return d


def build_report(root: Path = ROOT, out: Path | None = None, db: Path | None = None) -> Path:
    target = root / "target"
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    rr = json.loads((target / "run_results.json").read_text(encoding="utf-8"))
    nodes, edges = lineage(manifest)
    tests = []
    for r in rr["results"]:
        if r["unique_id"].startswith("test."):
            node = manifest["nodes"].get(r["unique_id"], {})
            tests.append([node.get("name", r["unique_id"]), r["status"], r.get("failures") or 0, round(r.get("execution_time", 0), 3)])
    tests.sort(key=lambda t: ({"fail": 0, "error": 0, "warn": 1}.get(t[1], 2), t[0]))
    hist = []
    hp = root / "runs" / "history.csv"
    if hp.exists():
        with hp.open(encoding="utf-8", newline="") as f:
            hist = list(csv.DictReader(f))
    data = collect_data(db or target / "warehouse.duckdb")
    data.update({
        "generated": rr["metadata"]["generated_at"][:19].replace("T", " "),
        "models": sum(n["kind"] not in ("source", "seed") for n in nodes),
        "tests": tests, "history": hist[-60:], "lineage_svg": _svg(nodes, edges),
        "legend": [[k, c] for k, c in COLOR.items()],
    })
    tpl = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")
    doc = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    out = out or root / "docs" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out
