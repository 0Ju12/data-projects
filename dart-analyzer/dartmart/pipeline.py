"""수집 → 정규화 → SQLite 마트 → 리포트

python -m dartmart.pipeline build   # DART_API_KEY 필요. config.json 의 회사·연도
python -m dartmart.pipeline report  # 마트에서 지표 표(Markdown) 생성
python -m dartmart.pipeline ask "포스코인터내셔널" "LNG 사업 투자"   # 사업보고서 문단 검색
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path

from . import parse, search
from .client import DartError

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def resolve(corps: list[dict], names: list[str], log=print) -> dict[str, dict]:
    """회사 이름 → 고유번호. 상장사(stock_code 있음)를 우선. 못 찾거나 여럿이면 건너뛰고 알림 (전체 수집은 계속)"""
    out = {}
    for n in names:
        n, _, code = n.partition("#")                 # "회사명#종목코드" 로 같은 이름 회사를 구분
        hits = [c for c in corps if c["corp_name"] == n and (not code or c["stock_code"] == code)]
        listed = [c for c in hits if c["stock_code"]]
        pick = listed or hits
        if len(pick) != 1:
            log(f"⚠ '{n}' 고유번호를 하나로 정할 수 없어 건너뜀 (후보 {len(pick)}개) — config.json 의 이름을 DART 표기로 고치세요")
            continue
        out[n] = pick[0]
    return out


def load(con, client, cfg: dict, years: list[int], with_docs: bool = True, log=print) -> dict:
    corps = client.corp_codes()
    stats = {"companies": 0, "financial_rows": 0, "filings": 0, "paragraphs": 0}
    for sector, names in cfg["companies"].items():
        for name, c in resolve(corps, names, log).items():
            con.execute("INSERT OR REPLACE INTO companies VALUES (?,?,?,?)", (c["corp_code"], c["corp_name"], c["stock_code"], sector))
            stats["companies"] += 1
            for y in years:
                rows = parse.normalize_financials(client.financials(c["corp_code"], y))
                con.executemany("INSERT OR REPLACE INTO financials VALUES (:corp_code,:bsns_year,:account,:fs_div,:amount,:prev_amount,:rcept_no)", rows)
                stats["financial_rows"] += len(rows)
            if with_docs:
                fl = [f for f in client.filings(c["corp_code"], f"{max(years)}0101", date.today().strftime("%Y%m%d")) if "사업보고서" in f["report_nm"]]
                for f in fl[:1]:                           # 가장 최근 사업보고서 1건
                    con.execute("INSERT OR REPLACE INTO filings VALUES (?,?,?,?)", (f["rcept_no"], c["corp_code"], f["report_nm"], f["rcept_dt"]))
                    stats["filings"] += 1
                    try:
                        paras = [p for x in client.document(f["rcept_no"]) for p in parse.document_sections(x)]
                    except DartError as e:                 # 원문 하나가 없어도 전체 수집은 계속
                        log(f"⚠ {name} 원문 건너뜀: {e}")
                        paras = []
                    con.executemany("INSERT OR REPLACE INTO paragraphs VALUES (?,?,?,?)", [(f["rcept_no"], i, p["section"], p["text"]) for i, p in enumerate(paras)])
                    stats["paragraphs"] += len(paras)
            log(f"✔ {name}")
    con.commit()
    return stats


def report(con) -> str:
    rows = con.execute("SELECT corp_name, sector, bsns_year, revenue, operating_income, op_margin_pct, revenue_yoy_pct FROM v_growth ORDER BY sector, corp_name, bsns_year").fetchall()
    fmt = lambda v: "—" if v is None else f"{v / 1e8:,.0f}"
    lines = ["| 분류 | 회사 | 연도 | 매출(억원) | 영업이익(억원) | 영업이익률 | 매출 증감 |", "|---|---|---|---|---|---|---|"]
    for n, s, y, r, o, m, g in rows:
        lines.append(f"| {s} | {n} | {y} | {fmt(r)} | {fmt(o)} | {'—' if m is None else f'{m}%'} | {'—' if g is None else f'{g:+}%'} |")
    return "\n".join(lines)


def ask(con, corp_name: str, query: str, k: int = 3) -> list[dict]:
    rows = con.execute("""SELECT p.text, p.section, f.report_nm, f.rcept_no FROM paragraphs p JOIN filings f USING (rcept_no)
                          JOIN companies c USING (corp_code) WHERE c.corp_name = ?""", (corp_name,)).fetchall()
    paras = [{"text": t, "section": s, "report_nm": r, "rcept_no": n} for t, s, r, n in rows]
    return search.search(paras, query, k)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "report", "ask"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--db", default=str(ROOT / "data" / "dart.sqlite"))
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    a = ap.parse_args(argv)
    Path(a.db).parent.mkdir(parents=True, exist_ok=True)
    con = connect(Path(a.db))
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    if a.cmd == "build":
        from .client import Client
        print(json.dumps(load(con, Client(), cfg, cfg["years"]), ensure_ascii=False))
        (ROOT / "reports").mkdir(exist_ok=True)
        (ROOT / "reports" / "metrics.md").write_text(report(con) + "\n", encoding="utf-8")
    elif a.cmd == "report":
        print(report(con))
    else:
        for h in ask(con, a.args[0], " ".join(a.args[1:])) or [{"text": "근거 없음 — 사업보고서에서 관련 문단을 찾지 못했습니다.", "section": "", "report_nm": "", "rcept_no": "", "score": 0}]:
            print(f"[{h['score']}] {h['report_nm']} · {h['section']}\n  {h['text'][:300]}\n  https://dart.fss.or.kr/dsaf001/main.do?rcpNo={h['rcept_no']}\n")


if __name__ == "__main__":
    main()
