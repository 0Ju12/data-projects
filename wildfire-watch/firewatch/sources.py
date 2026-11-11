"""상시 열원(제철소·시멘트 공장·석유화학 단지 등) 가려내기.

위성은 불과 뜨거운 설비를 구분하지 못합니다. 한국에서는 탐지의 대부분이 같은 자리에서
반복되는 산업 시설이라, 그대로 두면 '화재'가 매일 같은 곳에서 나는 것처럼 보입니다.

규칙: 약 1 km 칸(위·경도 0.01°)에서 서로 다른 날 MIN_DAYS 일 이상 탐지되면 상시 열원으로
보고, 한 번 그렇게 판정한 자리는 목록(data/static_sources.csv)에 남깁니다. 그 자리에서
RADIUS_KM 안의 탐지도 같은 열원으로 봅니다.
한계: 여러 날 이어지는 큰 산불도 같은 자리에서 반복 탐지될 수 있어 잘못 걸러질 수 있습니다.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from . import grid

MIN_DAYS = 3
RADIUS_KM = 1.5


def spot(lat: float, lon: float) -> tuple[float, float]:
    return round(lat, 2), round(lon, 2)


def find(detections: list[dict]) -> dict[tuple[float, float], int]:
    days = defaultdict(set)
    for d in detections:
        days[spot(d["lat"], d["lon"])].add(d["date"])
    return {s: len(v) for s, v in days.items() if len(v) >= MIN_DAYS}


def load(path: Path) -> dict[tuple[float, float], int]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {(float(r["lat"]), float(r["lon"])): int(r["days"]) for r in csv.DictReader(f)}


def update(path: Path, detections: list[dict]) -> dict[tuple[float, float], int]:
    known = load(path)
    for s, n in find(detections).items():
        known[s] = max(n, known.get(s, 0))
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lat", "lon", "days", "near"])
        for (a, b), n in sorted(known.items()):
            w.writerow([f"{a:.2f}", f"{b:.2f}", n, grid.near_city(a, b)])
    return known


def is_static(d: dict, known) -> bool:
    a, b = spot(d["lat"], d["lon"])
    for da in (-0.02, -0.01, 0, 0.01, 0.02):
        for db in (-0.02, -0.01, 0, 0.01, 0.02):
            s = (round(a + da, 2), round(b + db, 2))
            if s in known and grid.km(d["lat"], d["lon"], *s) <= RADIUS_KM:
                return True
    return False
