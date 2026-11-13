"""명령줄 — Airflow 없이도 같은 일을 합니다.

python -m wh.cli run --date 2025-03-01            # 하루 실행
python -m wh.cli backfill 2025-03-01 2025-03-07   # 과거 날짜 다시 채우기 (dbt 는 한 번, 내보내기는 날짜마다)
python -m wh.cli report                           # 계보·테스트 결과·실행 기록 보고서 (docs/index.html)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from . import pipeline as P
from .report import build_report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wh")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--date", default=date.today().isoformat())
    r.add_argument("--export-date", help="내보낼 날짜를 직접 지정 (기본: 실행 날짜의 월·일을 자료가 있는 2025년으로 옮김)")
    b = sub.add_parser("backfill")
    b.add_argument("start")
    b.add_argument("end")
    sub.add_parser("report")
    a = ap.parse_args(argv)

    if a.cmd == "run":
        row = P.run(a.date, export_day_override=a.export_date)
        print(json.dumps(row, ensure_ascii=False, indent=1))
        return 0 if row["status"] == "success" else 1
    if a.cmd == "backfill":
        db = str(P.ROOT / "target" / "warehouse.duckdb")
        P.check_sources()
        p = P.dbt(["build"], db=db)
        if p.returncode != 0:
            print(p.stdout[-2000:])
            return 1
        tot = 0
        for d in P.daterange(a.start, a.end):
            e = P.export_day(d, db, P.ROOT / "exports")
            tot += e["rows"]
            print(d, e["rows"], e["sha"])
        print("합계 행", tot)
        return 0
    if a.cmd == "report":
        out = build_report()
        print("보고서:", out)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
