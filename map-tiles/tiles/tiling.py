"""경위도 → 웹 메르카토르 타일 좌표, 점·사각 칸을 타일로 나누기."""

from __future__ import annotations

import math
from collections import defaultdict

from .mvt import POINT, POLYGON, Layer

EXTENT = 4096
BUFFER = 64  # 타일 경계에서 잘린 원·선이 끊겨 보이지 않게 이웃 타일 영역을 조금 겹침


def world_xy(lon: float, lat: float, z: int) -> tuple[float, float]:
    """줌 z 에서 세계 전체를 (2^z × EXTENT) 정수 평면으로 본 좌표."""
    n = (1 << z) * EXTENT
    lat = max(-85.05112878, min(85.05112878, lat))
    x = (lon + 180.0) / 360.0 * n
    r = math.radians(lat)
    y = (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n
    return x, y


class TileSet:
    """(z, x, y) → 레이어 이름 → Layer. 레이어 순서는 처음 넣은 순서."""

    def __init__(self):
        self.tiles: dict[tuple[int, int, int], dict[str, Layer]] = defaultdict(dict)
        self.counts: dict[str, int] = defaultdict(int)

    def _layer(self, key, name):
        t = self.tiles[key]
        if name not in t:
            t[name] = Layer(name, EXTENT)
        return t[name]

    def add_point(self, name: str, z: int, lon: float, lat: float, props: dict, fid: int | None = None) -> None:
        X, Y = world_xy(lon, lat, z)
        tx, ty = int(X // EXTENT), int(Y // EXTENT)
        lim = 1 << z
        for dx in (-1, 0, 1):  # 경계 근처 점은 이웃 타일 버퍼에도
            for dy in (-1, 0, 1):
                x, y = tx + dx, ty + dy
                if not (0 <= x < lim and 0 <= y < lim):
                    continue
                px, py = round(X - x * EXTENT), round(Y - y * EXTENT)
                if -BUFFER <= px <= EXTENT + BUFFER and -BUFFER <= py <= EXTENT + BUFFER:
                    self._layer((z, x, y), name).add(POINT, [[(px, py)]], props, fid)
                    self.counts[f"{name}@{z}"] += dx == 0 and dy == 0

    def add_box(self, name: str, z: int, west: float, south: float, east: float, north: float, props: dict) -> None:
        """경위도 사각 칸(격자 한 칸)을 걸치는 모든 타일에, 타일 경계(+버퍼)로 잘라 넣음."""
        x0, y0 = world_xy(west, north, z)
        x1, y1 = world_xy(east, south, z)
        lim = 1 << z
        for tx in range(max(0, int(x0 // EXTENT)), min(lim - 1, int(x1 // EXTENT)) + 1):
            for ty in range(max(0, int(y0 // EXTENT)), min(lim - 1, int(y1 // EXTENT)) + 1):
                ox, oy = tx * EXTENT, ty * EXTENT
                a = max(-BUFFER, round(x0 - ox))
                b = min(EXTENT + BUFFER, round(x1 - ox))
                c = max(-BUFFER, round(y0 - oy))
                d = min(EXTENT + BUFFER, round(y1 - oy))
                if b <= a or d <= c:
                    continue
                ring = [(a, c), (b, c), (b, d), (a, d)]  # 타일 좌표에서 시계 방향 = 바깥 고리
                self._layer((z, tx, ty), name).add(POLYGON, [ring], props)
        self.counts[f"{name}@{z}"] += 1

    def encode(self) -> dict[tuple[int, int, int], bytes]:
        from .mvt import encode_tile

        return {k: encode_tile(list(v.values())) for k, v in self.tiles.items()}
