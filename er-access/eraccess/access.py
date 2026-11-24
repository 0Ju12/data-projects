"""인구 칸마다 가장 가까운 응급실까지의 차량 이동 시간과, 기준 시간 안에 닿는 인구 비율."""
from __future__ import annotations

from .geo import PointIndex
from .graph import RoadGraph, multi_source_dijkstra


def _snap_cost(dist_m: float, access_kmh: float) -> float:
    """도로망에 붙이기까지의 직선 거리를 느린 속도로 환산한 초. 골목·진입로 몫의 근사."""
    return dist_m / (access_kmh / 3.6)


class Network:
    """그래프·점 색인·뒤집힌 그래프·칸 붙이기 결과를 한 번만 만들어 여러 대상(응급실 종별)에 재사용한다."""

    def __init__(self, g: RoadGraph, cells: list[dict], snap_m: float, access_kmh: float):
        self.g, self.cells, self.snap_m, self.access_kmh = g, cells, snap_m, access_kmh
        self.idx = PointIndex(g.nodes)
        self.rev = g.reversed()             # 칸 → 응급실 시간을 응급실 쪽에서 한 번에 풀기 위해
        self.snapped = [self.idx.nearest(c["lat"], c["lon"], snap_m) for c in cells]

    def travel_times(self, ers: list[dict], tiers: list[str], cutoff_min: float | None = None):
        """tiers 에 속한 응급실 중 가장 가까운 곳까지의 분. 도로에 못 붙거나 cutoff 안에 못 닿으면 None.
        반환: (분 목록, 가장 가까운 응급실의 ers 안 번호 목록, 정보)."""
        sources: dict[int, float] = {}
        origin: dict[int, int] = {}
        unsnapped = []
        for k, e in enumerate(ers):
            if e["tier"] not in tiers:
                continue
            hit = self.idx.nearest(e["lat"], e["lon"], self.snap_m)
            if hit is None:
                unsnapped.append(e["name"])
                continue
            node, d = hit
            cost = _snap_cost(d, self.access_kmh)
            if node not in sources or cost < sources[node]:
                sources[node], origin[node] = cost, k
        cutoff = None if cutoff_min is None else cutoff_min * 60
        reached = multi_source_dijkstra(self.rev, sources, cutoff) if sources else {}
        minutes: list[float | None] = []
        nearest: list[int | None] = []
        for hit in self.snapped:
            r = reached.get(hit[0]) if hit else None
            if r is None:
                minutes.append(None)
                nearest.append(None)
            else:
                minutes.append((r[0] + _snap_cost(hit[1], self.access_kmh)) / 60)
                nearest.append(origin[r[1]])
        info = {"targets": sum(e["tier"] in tiers for e in ers), "targets_unsnapped": unsnapped,
                "cells_no_road": sum(h is None for h in self.snapped)}
        return minutes, nearest, info


def coverage(cells: list[dict], minutes: list[float | None], limit_min: float) -> dict:
    """기준 시간 안에 닿는 인구 비율. 도로에 못 붙은 칸도 '못 닿음' 으로 센다 (보수적)."""
    total = sum(c["pop"] for c in cells)
    within = sum(c["pop"] for c, m in zip(cells, minutes) if m is not None and m <= limit_min)
    unknown = sum(c["pop"] for c, m in zip(cells, minutes) if m is None)
    return {
        "limit_min": limit_min,
        "population": round(total),
        "within": round(within),
        "share_within": round(within / total, 4) if total else None,
        "population_unreached": round(unknown),
    }


BANDS = [15, 30, 60, 90]           # 지도 색 구간과 같게 (30·60분 기준이 경계에 오도록)


def bands(cells: list[dict], minutes: list[float | None]) -> list[dict]:
    """이동 시간 구간별 인구. 마지막 두 칸은 '90분 넘음' 과 '못 닿음'."""
    edges = [0, *BANDS]
    out = [{"label": f"{a}–{b}분", "pop": 0.0} for a, b in zip(edges, edges[1:])]
    out += [{"label": f"{BANDS[-1]}분 넘음", "pop": 0.0}, {"label": "못 닿음", "pop": 0.0}]
    for c, m in zip(cells, minutes):
        if m is None:
            out[-1]["pop"] += c["pop"]
            continue
        k = next((i for i, b in enumerate(BANDS) if m <= b), len(BANDS))
        out[k]["pop"] += c["pop"]
    for b in out:
        b["pop"] = round(b["pop"])
    return out


def weighted_median(cells: list[dict], minutes: list[float | None]) -> float | None:
    """인구 가중 중앙값(분). 못 닿는 칸은 '아주 큼' 으로 보고 넣는다 — 빼면 사각지대가 가려진다."""
    pairs = sorted(((m if m is not None else float("inf")), c["pop"]) for c, m in zip(cells, minutes))
    total = sum(p for _, p in pairs)
    if not total:
        return None
    acc = 0.0
    for m, p in pairs:
        acc += p
        if acc >= total / 2:
            return None if m == float("inf") else round(m, 1)
    return None
