"""웨어하우스 실행 단계 — Airflow 작업과 명령줄(wh.cli)이 같은 함수를 부릅니다.

단계: 원본 확인 → dbt build(모델·테스트·변경 이력) → 날짜 파티션 내보내기 → 실행 기록
모든 단계는 같은 날짜로 다시 돌려도 결과가 같도록(멱등) 만들었습니다.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {
    "quakes_csv": ("../geo-data-pipeline/data/events.csv", ["id", "time_utc", "updated", "mag", "place"]),
    "demand_csv": ("../power-demand/data/kpx_hourly_demand_2025.csv", ["날짜", "1시", "24시"]),
    "weather_csv": ("../power-demand/data/weather_2025.csv", ["time", "mean"]),
    "jobs_csv": ("data/jobs.csv", ["source", "job_id", "title", "posted_at_utc", "skills", "skills_dict", "first_seen", "last_seen"]),
    "jobs_fetch_csv": ("data/jobs_fetch_log.csv", ["run_date", "source", "fetched", "overlap"]),
}
RUN_FIELDS = ["run_at_utc", "logical_date", "status", "models", "tests_pass", "tests_warn", "tests_fail",
              "seconds", "rows_demand_hourly", "rows_quakes", "snapshot_versions", "exported_rows", "sources_sha", "rows_jobs"]


class SourceError(RuntimeError):
    """원본 파일이 없거나 약속한 열이 빠졌을 때"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def check_sources(vars_: dict | None = None, root: Path = ROOT) -> dict:
    """원본이 있고, 필요한 열이 있고, 비어 있지 않은지 확인 (스키마가 바뀌면 dbt 를 돌리기 전에 멈춤)"""
    out = {}
    for key, (default, need) in SOURCES.items():
        p = (root / (vars_ or {}).get(key, default)).resolve()
        if not p.exists():
            raise SourceError(f"{key}: 파일 없음 — {p}")
        with p.open(encoding="utf-8-sig", newline="") as f:
            r = csv.reader(f)
            header = next(r, None) or []
            rows = sum(1 for _ in r)
        missing = [c for c in need if c not in header]
        if missing:
            raise SourceError(f"{key}: 열이 빠짐 {missing} (지금 열: {header[:8]}…)")
        if rows == 0:
            raise SourceError(f"{key}: 자료 행이 0")
        out[key] = {"path": str(p), "rows": rows, "columns": len(header), "sha": _sha(p)}
    return out


def dbt(args: list[str], vars_: dict | None = None, db: str | None = None, root: Path = ROOT, target_path: str | None = None):
    """dbt 를 하위 프로세스로 실행. DBT_BIN 환경변수로 다른 가상환경의 dbt 를 가리킬 수 있습니다 (Airflow 와 분리)."""
    cmd = [os.environ.get("DBT_BIN", "dbt"), *args, "--profiles-dir", str(root), "--project-dir", str(root)]
    if target_path:
        cmd += ["--target-path", target_path]
    if vars_:
        cmd += ["--vars", json.dumps(vars_, ensure_ascii=False)]
    env = dict(os.environ)
    if db:
        env["WH_DB"] = db
    return subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)


def run_results(target: Path) -> dict:
    """dbt 가 남긴 run_results.json 을 요약"""
    rr = json.loads((target / "run_results.json").read_text(encoding="utf-8"))
    s = {"models": 0, "tests_pass": 0, "tests_warn": 0, "tests_fail": 0, "failed": [], "seconds": round(rr.get("elapsed_time", 0), 2)}
    for r in rr["results"]:
        kind, st = r["unique_id"].split(".")[0], r["status"]
        if kind in ("model", "snapshot", "seed") and st == "success":
            s["models"] += 1
        elif kind == "test":
            s["tests_pass" if st == "pass" else "tests_warn" if st == "warn" else "tests_fail"] += 1
        if st in ("error", "fail"):
            s["failed"].append(r["unique_id"].split(".")[-1] if kind != "test" else r["unique_id"].split(".")[2])
    return s


def _connect(db: str, read_only=True):
    import duckdb
    return duckdb.connect(db, read_only=read_only)


def export_day(day: str, db: str, out_dir: Path) -> dict:
    """하루치 시간별 수요를 날짜 파티션 폴더에 Parquet 로 내보냅니다.

    임시 파일에 쓴 뒤 바꿔치기하고, 정렬·압축을 고정해 같은 날짜를 몇 번 돌려도 같은 파일이 됩니다.
    자료에 없는 날짜는 빈 파일을 만들지 않고 0행으로 보고합니다.
    """
    date.fromisoformat(day)                      # 형식 확인 (SQL 에 그대로 넣지 않도록)
    con = _connect(db)
    try:
        n = con.execute("select count(*) from fct_demand_hourly where demand_date = ?", [day]).fetchall()[0][0]
        part = out_dir / "fct_demand_hourly" / f"demand_date={day}"
        if n == 0:
            if part.exists():
                shutil.rmtree(part)
            return {"day": day, "rows": 0, "path": None, "sha": None}
        part.mkdir(parents=True, exist_ok=True)
        tmp, final = part / ".part.tmp.parquet", part / "part.parquet"
        con.execute(
            f"copy (select hour_start_kst, hour_ending, demand_mw, temp_mean from fct_demand_hourly "
            f"where demand_date = '{day}' order by hour_start_kst) to '{tmp.as_posix()}' (format parquet, compression zstd)")
        os.replace(tmp, final)
        return {"day": day, "rows": n, "path": str(final), "sha": _sha(final)}
    finally:
        con.close()


def daterange(start: str, end: str):
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if b < a:
        raise ValueError("끝 날짜가 시작보다 앞섭니다")
    while a <= b:
        yield a.isoformat()
        a += timedelta(days=1)


def table_counts(db: str) -> dict:
    con = _connect(db)
    try:
        q = lambda s: con.execute(s).fetchall()[0][0]
        return {"rows_demand_hourly": q("select count(*) from fct_demand_hourly"),
                "rows_quakes": q("select count(*) from stg_quakes"),
                "snapshot_versions": q("select count(*) from snap_quakes"),
                "rows_jobs": q("select count(*) from fct_job_postings")}
    finally:
        con.close()


def restore_state(db: str, state: Path) -> int:
    """변경 이력 표를 저장해 둔 파일에서 되살립니다.

    CI 는 매번 빈 DB 에서 시작하므로, 이력을 state/snap_quakes.parquet 로 저장소에 남기고 실행 전에 다시 넣습니다.
    이렇게 해야 어제까지 쌓인 판 위에 오늘의 변경이 이어집니다.
    """
    Path(db).parent.mkdir(parents=True, exist_ok=True)   # 처음 실행이면 DB 폴더가 아직 없음
    f = state / "snap_quakes.parquet"
    if not f.exists():
        return 0
    con = _connect(db, read_only=False)
    try:
        con.execute(f"create or replace table snap_quakes as select * from read_parquet('{f.as_posix()}')")
        return con.execute("select count(*) from snap_quakes").fetchall()[0][0]
    finally:
        con.close()


def save_state(db: str, state: Path) -> int:
    """변경 이력 표를 정렬해 파일로 저장 (내용이 같으면 파일도 같도록)"""
    state.mkdir(parents=True, exist_ok=True)
    tmp, final = state / ".snap.tmp.parquet", state / "snap_quakes.parquet"
    con = _connect(db)
    try:
        con.execute(f"copy (select * from snap_quakes order by quake_id, dbt_valid_from) to '{tmp.as_posix()}' (format parquet, compression zstd)")
        n = con.execute("select count(*) from snap_quakes").fetchall()[0][0]
    finally:
        con.close()
    os.replace(tmp, final)
    return n


def map_to_data_year(day: str, year: int = 2025) -> str:
    """수요 자료가 한 해뿐이라, 실행 날짜의 월·일을 자료가 있는 해로 옮깁니다 (2월 29일 → 28일)"""
    d = date.fromisoformat(day)
    return f"{year}-02-28" if (d.month, d.day) == (2, 29) else f"{year}-{d.month:02d}-{d.day:02d}"


def record_run(history: Path, row: dict) -> None:
    """실행 한 번을 runs/history.csv 에 한 줄로 남김 (같은 날짜를 다시 돌리면 그 날짜 줄을 바꿈 → 재실행해도 줄이 늘지 않음)"""
    history.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if history.exists():
        with history.open(encoding="utf-8", newline="") as f:
            rows = [{k: r.get(k, "") for k in RUN_FIELDS} for r in csv.DictReader(f) if r.get("logical_date") != row["logical_date"]]
    rows.append({k: row.get(k, "") for k in RUN_FIELDS})
    rows.sort(key=lambda r: r["logical_date"])
    tmp = history.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RUN_FIELDS)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, history)


def run(day: str, db: str | None = None, vars_: dict | None = None, out_dir: Path | None = None,
        history: Path | None = None, root: Path = ROOT, export_day_override: str | None = None,
        state: Path | None = None) -> dict:
    """하루치 전체 실행. 실패해도 실행 기록은 남깁니다."""
    db = db or str(root / "target" / "warehouse.duckdb")
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    out_dir = out_dir or root / "exports"
    history = history or root / "runs" / "history.csv"
    state = state or root / "state"
    t0 = time.time()
    row = {"run_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "logical_date": day, "status": "failed"}
    try:
        src = check_sources(vars_, root)
        row["sources_sha"] = "-".join(v["sha"][:6] for v in src.values())
        restore_state(db, state)
        p = dbt(["build"], vars_, db, root)
        target = root / "target"
        if (target / "run_results.json").exists():
            row.update({k: v for k, v in run_results(target).items() if k in RUN_FIELDS})
        if p.returncode != 0:
            row["error"] = (p.stdout or p.stderr)[-1500:]
            return row
        save_state(db, state)
        row.update(table_counts(db))
        row["exported_rows"] = export_day(export_day_override or map_to_data_year(day), db, out_dir)["rows"]
        row["status"] = "success"
        return row
    except SourceError as e:
        row["error"] = str(e)
        return row
    finally:
        row["seconds"] = round(time.time() - t0, 2)
        record_run(history, row)


if __name__ == "__main__":   # python -m wh.pipeline 2025-03-01
    r = run(sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat())
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(0 if r["status"] == "success" else 1)
