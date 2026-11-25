"""er-access 의 계산 결과(docs/finder.json)를 웹앱용 작은 격자 파일로 → docs/grid.json (+ 병상 스냅숏이 있으면 docs/beds.json)

    python build.py

grid.json
- 칸 번호 i = floor(위도 / 칸), j = floor(경도 / 칸) 를 (i0, j0) 기준 차이로
- cells: 칸마다 [di, dj, 대상1 분×10, 대상1 응급실 번호, 대상2 …] 를 이어 붙인 정수 배열 (값 없음 = -1)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "er-access/docs/finder.json"
BEDS_DIR = ROOT / "er-access/data/beds"
OUT = HERE / "docs"
TIER_KO = {"regional": "권역응급의료센터", "local_center": "지역응급의료센터", "local_institution": "지역응급의료기관", "other": "응급실 (임시 목록)"}


def compact(finder: dict) -> dict:
    deg = finder["cell_deg"]
    nt = len(finder["targets"])
    ij = [(round(c[0] / deg - 0.5), round(c[1] / deg - 0.5)) for c in finder["cells"]]
    i0, j0 = min(i for i, _ in ij), min(j for _, j in ij)
    flat: list[int] = []
    for (i, j), c in zip(ij, finder["cells"]):
        flat += [i - i0, j - j0]
        for t in range(nt):
            m, k = c[2 + 2 * t], c[3 + 2 * t]
            flat += [-1 if m is None else round(m * 10), -1 if k is None else k]
    return {"built": finder.get("built"), "er_source": finder.get("er_source"), "deg": deg, "i0": i0, "j0": j0, "stride": 2 + 2 * nt,
            "targets": finder["targets"], "ers": [[n, la, lo, t, TIER_KO.get(t, t)] for n, la, lo, t in finder["ers"]], "cells": flat}


def latest_beds(beds_dir: Path = BEDS_DIR) -> dict | None:
    """korea-fetch 로 모은 병상 스냅숏 중 가장 최근 시각의 행 → {기관명: {hvec, hvidate, collected_at}}. 없으면 None."""
    files = sorted(beds_dir.glob("*.csv")) if beds_dir.exists() else []
    if not files:
        return None
    with files[-1].open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    last = max(r.get("collected_at", "") for r in rows)
    out = {}
    for r in rows:
        if r.get("collected_at", "") == last and r.get("dutyName"):
            out[r["dutyName"]] = {"hvec": r.get("hvec"), "hvidate": r.get("hvidate"), "collected_at": last}
    return {"collected_at": last, "by_name": out}


def build(src: Path = SRC, out: Path = OUT) -> dict:
    finder = json.loads(src.read_text(encoding="utf-8"))
    grid = compact(finder)
    beds = latest_beds()
    grid["beds"] = bool(beds)
    out.mkdir(parents=True, exist_ok=True)
    (out / "grid.json").write_text(json.dumps(grid, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if beds:
        (out / "beds.json").write_text(json.dumps(beds, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"cells": len(finder["cells"]), "ers": len(grid["ers"]), "targets": [t["name"] for t in grid["targets"]],
            "bytes": (out / "grid.json").stat().st_size, "beds": bool(beds)}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
