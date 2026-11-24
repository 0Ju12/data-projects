"""격자 집계 → Getis-Ord Gi* → 다중 검정 보정(BH) → 붙어 있는 핫스팟 칸을 구역으로 묶기.

Gi* 는 '이 칸과 이웃 칸을 합친 사고 수가, 분석 범위 전체 평균으로 기대되는 것보다 얼마나 많은가' 를 z 점수로 나타낸다.
칸이 수만 개라 0.05 로 하나씩 검정하면 우연한 핫스팟이 수백 개 나온다 → Benjamini–Hochberg 로 거짓 발견 비율을 묶는다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .utmk import to_wgs84


@dataclass
class Grid:
    x0: float           # 왼쪽 아래 모서리 (UTM-K m)
    y0: float
    cell: float         # 칸 한 변 (m)
    counts: np.ndarray  # [행(y), 열(x)]

    def center(self, i: int, j: int) -> tuple[float, float]:
        """칸 (행 i, 열 j) 중심의 위경도."""
        return to_wgs84(self.x0 + (j + 0.5) * self.cell, self.y0 + (i + 0.5) * self.cell)


def make_grid(points: list[dict], cell_m: float, weight: str | None = None) -> Grid:
    xs = np.array([p["x"] for p in points])
    ys = np.array([p["y"] for p in points])
    x0, y0 = math.floor(xs.min() / cell_m) * cell_m, math.floor(ys.min() / cell_m) * cell_m
    j = ((xs - x0) // cell_m).astype(int)
    i = ((ys - y0) // cell_m).astype(int)
    w = np.array([p.get(weight) or 0 for p in points], dtype=float) if weight else np.ones(len(points))
    counts = np.zeros((i.max() + 1, j.max() + 1))
    np.add.at(counts, (i, j), w)
    return Grid(x0, y0, cell_m, counts)


def _offsets(band_m: float, cell_m: float) -> list[tuple[int, int]]:
    """칸 중심 사이 거리가 band_m 이하인 (di, dj). 자기 자신 포함 (Gi* 의 '*')."""
    r = int(band_m // cell_m)
    return [(di, dj) for di in range(-r, r + 1) for dj in range(-r, r + 1)
            if math.hypot(di, dj) * cell_m <= band_m + 1e-9]


def _window_sum(a: np.ndarray, offsets: list[tuple[int, int]]) -> np.ndarray:
    r = max(max(abs(di), abs(dj)) for di, dj in offsets)
    p = np.pad(a, r)
    h, w = a.shape
    out = np.zeros_like(a, dtype=float)
    for di, dj in offsets:
        out += p[r + di:r + di + h, r + dj:r + dj + w]
    return out


def study_mask(g: Grid, band_m: float) -> np.ndarray:
    """분석에 넣을 칸: 사고가 한 번이라도 난 칸에서 band_m 안. 바다·산지처럼 도로가 없는 빈 칸이
    평균을 끌어내려 도시 전체가 핫스팟이 되는 것을 막는 근사다. (도로망 칸으로 바꾸는 것이 다음 단계)"""
    return _window_sum((g.counts > 0).astype(float), _offsets(band_m, g.cell)) > 0


def gi_star(g: Grid, band_m: float, mask: np.ndarray | None = None) -> np.ndarray:
    """이진 가중(거리 band_m 안 = 1) Gi* z 점수. mask 밖 칸은 NaN."""
    mask = study_mask(g, band_m) if mask is None else mask
    x = np.where(mask, g.counts, 0.0)
    n = int(mask.sum())
    xbar = x[mask].mean()
    s = math.sqrt(max((x[mask] ** 2).mean() - xbar ** 2, 0.0))
    offs = _offsets(band_m, g.cell)
    lsum = _window_sum(x, offs)                         # 이웃(자신 포함) 사고 합
    wsum = _window_sum(mask.astype(float), offs)        # 이웃(자신 포함) 칸 수 — 이진 가중이라 Σw² 도 같다
    denom = s * np.sqrt(np.maximum(n * wsum - wsum ** 2, 0.0) / (n - 1))
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (lsum - xbar * wsum) / denom
    z[~mask] = np.nan
    return z


def bh_hot(z: np.ndarray, q: float = 0.05) -> np.ndarray:
    """단측(많은 쪽) p 값에 Benjamini–Hochberg 를 적용해 유의한 칸 True."""
    valid = ~np.isnan(z)
    zs = z[valid]
    p = np.array([0.5 * math.erfc(v / math.sqrt(2)) for v in zs])
    m = len(p)
    order = np.argsort(p)
    passed = p[order] <= q * np.arange(1, m + 1) / m
    k = np.nonzero(passed)[0].max() + 1 if passed.any() else 0
    hot_flat = np.zeros(m, dtype=bool)
    hot_flat[order[:k]] = True
    out = np.zeros(z.shape, dtype=bool)
    out[valid] = hot_flat
    return out


def zones(g: Grid, hot: np.ndarray, z: np.ndarray) -> list[dict]:
    """맞닿은(8방향) 핫스팟 칸을 한 구역으로 묶어, 사고 수가 많은 순으로."""
    seen = np.zeros_like(hot)
    out = []
    for i0, j0 in zip(*np.nonzero(hot)):
        if seen[i0, j0]:
            continue
        stack, cells = [(i0, j0)], []
        seen[i0, j0] = True
        while stack:
            i, j = stack.pop()
            cells.append((i, j))
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    a, b = i + di, j + dj
                    if 0 <= a < hot.shape[0] and 0 <= b < hot.shape[1] and hot[a, b] and not seen[a, b]:
                        seen[a, b] = True
                        stack.append((a, b))
        crashes = float(sum(g.counts[i, j] for i, j in cells))
        wi = sum(g.counts[i, j] * i for i, j in cells) / crashes if crashes else np.mean([c[0] for c in cells])
        wj = sum(g.counts[i, j] * j for i, j in cells) / crashes if crashes else np.mean([c[1] for c in cells])
        lat, lon = to_wgs84(g.x0 + (wj + 0.5) * g.cell, g.y0 + (wi + 0.5) * g.cell)
        out.append({"cells": len(cells), "crashes": crashes, "max_z": round(float(max(z[i, j] for i, j in cells)), 2),
                    "lat": round(lat, 5), "lon": round(lon, 5)})
    return sorted(out, key=lambda d: (-d["crashes"], -d["max_z"]))
