"""Airflow DAG — 매일: 원본 확인 → dbt build → 날짜 파티션 내보내기 → 실행 기록 → 보고서

작업은 얇은 껍데기이고, 실제 일은 wh.pipeline 의 함수가 합니다 (명령줄·테스트와 같은 코드).
- 재시도: 원본 확인과 dbt 는 2번까지 다시 시도
- 과거 채우기: `airflow backfill create --dag-id warehouse_daily --from-date 2025-03-01 --to-date 2025-03-07`
- dbt 는 DBT_BIN 환경변수로 다른 가상환경의 것을 씁니다 (Airflow 와 의존성이 부딪히지 않게)
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import DAG, task

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB = str(ROOT / "target" / "warehouse.duckdb")

with DAG(
    dag_id="warehouse_daily",
    start_date=datetime(2025, 1, 1),
    schedule="20 21 * * *",          # 매일 06:20 KST — 지진 수집(06:17) 뒤
    catchup=False,
    max_active_runs=1,               # 같은 DuckDB 파일을 동시에 쓰지 않도록
    default_args={"retries": 2, "retry_delay": timedelta(seconds=20)},
    tags=["warehouse", "dbt"],
) as dag:

    @task
    def check_sources() -> dict:
        from wh import pipeline as P
        return P.check_sources()

    @task
    def dbt_build(src: dict) -> dict:
        from wh import pipeline as P
        P.restore_state(DB, ROOT / "state")          # 어제까지의 변경 이력 위에 이어 쌓기
        p = P.dbt(["build"], db=DB)
        summary = P.run_results(ROOT / "target")
        if p.returncode != 0:
            raise RuntimeError(f"dbt build 실패: {summary['failed']}\n{p.stdout[-1500:]}")
        P.save_state(DB, ROOT / "state")
        return summary

    @task(retries=0)
    def export_partition(summary: dict, ds: str | None = None) -> dict:
        """그날 파티션만 다시 씁니다. 수요 자료가 2025년뿐이라 실행 날짜의 월·일을 2025년으로 옮겨 내보냅니다."""
        from wh import pipeline as P
        return P.export_day(P.map_to_data_year(ds), DB, ROOT / "exports")

    @task(trigger_rule="all_done", retries=0)
    def record(ds: str | None = None, ti=None) -> None:
        """앞 단계가 실패해도 실행 기록은 남깁니다."""
        from wh import pipeline as P
        summary = ti.xcom_pull(task_ids="dbt_build") or {}
        exported = ti.xcom_pull(task_ids="export_partition") or {}
        row = {"run_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "logical_date": ds,
               "status": "success" if exported else "failed", "exported_rows": exported.get("rows", "")}
        row.update({k: v for k, v in summary.items() if k in P.RUN_FIELDS})
        if exported:
            row.update(P.table_counts(DB))
        P.record_run(ROOT / "runs" / "history.csv", row)

    @task(trigger_rule="all_done", retries=0)
    def report() -> str:
        from wh.report import build_report
        return str(build_report())

    s = check_sources()
    b = dbt_build(s)
    e = export_partition(b)
    e >> record() >> report()
