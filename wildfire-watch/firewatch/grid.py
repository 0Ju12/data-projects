"""0.25° 격자와 육지 판정.

격자 칸 id 는 남서쪽 모서리의 위·경도 ("36.25_128.50"). 칸의 중심이 한국 육지 경계
(Natural Earth 10m, 단순화) 안에 있을 때만 육지 칸으로 씁니다.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

STEP = 0.25
BBOX = (33.0, 38.75, 125.75, 129.75)          # lat_min, lat_max, lon_min, lon_max
OUTLINE = Path(__file__).resolve().parent.parent / "data" / "korea_outline.json"

CITIES = {
    "서울": (37.57, 126.98), "부산": (35.18, 129.08), "대구": (35.87, 128.60), "인천": (37.46, 126.71), "광주": (35.16, 126.85),
    "대전": (36.35, 127.38), "울산": (35.54, 129.31), "강릉": (37.75, 128.88), "춘천": (37.88, 127.73), "원주": (37.34, 127.92),
    "청주": (36.64, 127.49), "전주": (35.82, 127.15), "포항": (36.02, 129.34), "안동": (36.57, 128.73), "제주": (33.50, 126.53),
    "목포": (34.81, 126.39), "여수": (34.76, 127.66), "진주": (35.18, 128.11), "창원": (35.23, 128.68), "속초": (38.21, 128.59),
    "울진": (36.99, 129.40), "당진": (36.89, 126.63), "광양": (34.94, 127.70), "동해": (37.52, 129.11), "삼척": (37.45, 129.17),
    "수원": (37.26, 127.03), "충주": (36.99, 127.93), "군산": (35.97, 126.74), "순천": (34.95, 127.49), "경주": (35.86, 129.22),
    "상주": (36.41, 128.16), "영주": (36.81, 128.62), "서산": (36.78, 126.45), "구미": (36.12, 128.34),
}


@lru_cache(maxsize=1)
def rings() -> list[list[tuple[float, float]]]:
    return [[(x, y) for x, y in r] for r in json.loads(OUTLINE.read_text(encoding="utf-8"))["rings"]]


def in_ring(lon: float, lat: float, ring) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def on_land(lat: float, lon: float) -> bool:
    return any(in_ring(lon, lat, r) for r in rings())


def cell_id(lat: float, lon: float) -> str:
    a = math.floor(lat / STEP) * STEP
    b = math.floor(lon / STEP) * STEP
    return f"{a:.2f}_{b:.2f}"


def cell_center(cid: str) -> tuple[float, float]:
    a, b = map(float, cid.split("_"))
    return a + STEP / 2, b + STEP / 2


@lru_cache(maxsize=1)
def land_cells() -> list[str]:
    out = []
    lat = BBOX[0]
    while lat < BBOX[1]:
        lon = BBOX[2]
        while lon < BBOX[3]:
            if on_land(lat + STEP / 2, lon + STEP / 2):
                out.append(f"{lat:.2f}_{lon:.2f}")
            lon += STEP
        lat += STEP
    return out


def in_bbox(lat: float, lon: float) -> bool:
    return BBOX[0] <= lat < BBOX[1] and BBOX[2] <= lon < BBOX[3]


def km(lat1, lon1, lat2, lon2) -> float:
    """두 점 사이 거리(km), 좁은 범위용 평면 근사"""
    dy = (lat2 - lat1) * 111.2
    dx = (lon2 - lon1) * 111.2 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def near_city(lat: float, lon: float) -> str:
    name, d = min(((n, km(lat, lon, *c)) for n, c in CITIES.items()), key=lambda x: x[1])
    return f"{name} 부근" if d <= 60 else f"{lat:.2f}°N {lon:.2f}°E"
