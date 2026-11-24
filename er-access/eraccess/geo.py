"""거리 계산과 가장 가까운 도로 지점 찾기."""
from __future__ import annotations

import math

R_EARTH_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH_M * math.asin(math.sqrt(a))


class PointIndex:
    """점들을 격자 칸에 나눠 담아, 가장 가까운 점을 칸 몇 개만 보고 찾는다.

    셀 크기는 도(degree) 단위. 위도 36° 부근에서 0.01° 는 남북 약 1.1 km, 동서 약 0.9 km.
    """

    def __init__(self, points: dict, cell_deg: float = 0.01):
        self.cell = cell_deg
        self.points = points
        self.buckets: dict[tuple[int, int], list] = {}
        for key, (lat, lon) in points.items():
            self.buckets.setdefault(self._key(lat, lon), []).append(key)

    def _key(self, lat: float, lon: float) -> tuple[int, int]:
        return int(math.floor(lat / self.cell)), int(math.floor(lon / self.cell))

    def nearest(self, lat: float, lon: float, max_m: float) -> tuple[object, float] | None:
        """max_m 안에서 가장 가까운 점 (키, 거리 m). 없으면 None."""
        ci, cj = self._key(lat, lon)
        # 한 칸의 가장 짧은 변(동서 방향) 길이로 몇 칸까지 볼지 정한다
        side_m = self.cell * 111_320 * max(math.cos(math.radians(lat)), 0.1)
        reach = int(math.ceil(max_m / side_m))
        best, best_d = None, max_m
        for di in range(-reach, reach + 1):
            for dj in range(-reach, reach + 1):
                for key in self.buckets.get((ci + di, cj + dj), ()):
                    plat, plon = self.points[key]
                    d = haversine_m(lat, lon, plat, plon)
                    if d <= best_d:
                        best, best_d = key, d
        return None if best is None else (best, best_d)
