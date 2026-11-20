"""Ember 월별 발전량과 Our World in Data 연간 에너지 자료를 받아, 쓸 나라·열만 남겨 data/ 에 저장합니다.

    python -m etl.fetch

둘 다 키 없이 받는 공개 자료(CC BY 4.0)입니다. 원본은 각각 약 30MB·9MB 라 통째로 저장하지 않고,
받으면서 바로 걸러 수백 KB 로 줄입니다. 받다가 실패하거나 약속한 열이 없으면 이전 파일을 그대로 둡니다.
"""
from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

from .sources import EMBER_FROM, COUNTRIES, EMBER_COLS, EMBER_SOURCES, EMBER_URL, OWID_COLS, OWID_FROM_YEAR, OWID_URL

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


class SchemaError(RuntimeError):
    pass


def _open(url: str, timeout: int = 180):
    req = urllib.request.Request(url, headers={"User-Agent": "energy-transition-dashboard"})
    return io.TextIOWrapper(urllib.request.urlopen(req, timeout=timeout), encoding="utf-8", newline="")


def _write_atomic(path: Path, header: list[str], rows: list[list]) -> None:
    """임시 파일에 다 쓴 뒤 바꿔치기 — 중간에 실패해도 반쯤 쓴 파일이 남지 않음. 정렬해서 쓰므로 같은 원본이면 같은 파일."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(sorted(rows, key=lambda r: [str(x) for x in r[:3]]))
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def filter_ember(lines) -> list[list]:
    r = csv.DictReader(lines)
    missing = [c for c in EMBER_COLS if c not in (r.fieldnames or [])]
    if missing:
        raise SchemaError(f"Ember 열이 바뀌었습니다: {missing}")
    keep = {e for e, _ in COUNTRIES.values()}
    out = []
    for row in r:
        if row["Area"] in keep and row["Electricity source"] in EMBER_SOURCES and row["Date"] >= EMBER_FROM:
            out.append([row[c] for c in EMBER_COLS])
    if not out:
        raise SchemaError("Ember 자료에서 대상 나라를 하나도 찾지 못했습니다")
    return out


def filter_owid(lines) -> list[list]:
    r = csv.DictReader(lines)
    missing = [c for c in OWID_COLS if c not in (r.fieldnames or [])]
    if missing:
        raise SchemaError(f"OWID 열이 바뀌었습니다: {missing}")
    keep = {o for _, o in COUNTRIES.values()}
    out = [[row[c] for c in OWID_COLS] for row in r
           if row["country"] in keep and row["year"].isdigit() and int(row["year"]) >= OWID_FROM_YEAR]
    if not out:
        raise SchemaError("OWID 자료에서 대상 나라를 하나도 찾지 못했습니다")
    return out


def fetch_all(ember_url: str = EMBER_URL, owid_url: str = OWID_URL, data: Path = DATA) -> dict:
    report = {}
    for name, url, fn, header, fname in [
        ("ember", ember_url, filter_ember, list(EMBER_COLS.values()), "ember_monthly.csv"),
        ("owid", owid_url, filter_owid, OWID_COLS, "owid_yearly.csv"),
    ]:
        try:
            with (_open(url) if url.startswith("http") else open(url, encoding="utf-8", newline="")) as f:
                rows = fn(f)
            _write_atomic(data / fname, header, rows)
            report[name] = {"status": "ok", "rows": len(rows)}
        except Exception as e:  # 받기 실패·형식 변경 — 이전 파일 유지
            report[name] = {"status": "kept_previous", "error": f"{type(e).__name__}: {e}"[:300]}
    return report


if __name__ == "__main__":
    rep = fetch_all()
    print(rep)
    sys.exit(0 if all(v["status"] == "ok" for v in rep.values()) else 1)
