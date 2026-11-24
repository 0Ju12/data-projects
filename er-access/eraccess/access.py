"""인구 칸마다 가장 가까운 응급실까지의 차량 이동 시간과, 기준 시간 안에 닿는 인구 비율."""
from __future__ import annotations

from .geo import PointIndex
from .graph import RoadGraph, multi_source_dijkstra


def _snap_cost(dist_m: float, access_kmh: float) -> float:
    """도로망에 붙이기까지의 직선 거리를 느린 속도로 환산한 초. 골목·진입로 몫의 근사."""
    return dist_m / (access_kmh / 3.6)


def travel_times(g: RoadGraph, cells: list[dict], ers: list[dict], tiers: list[str],
                 snap_m: float, access_kmh: float, cutoff_min: float | None = None) -> tuple[list[float | None], list[str | None], dict]:
    """tiers 에 속한 응급실 중 가장 가까운 곳까지의 분. 도로에 못 붙거나 cutoff 안에 못 닿으면 None.

    응급실 쪽에서 뒤집힌 그래프로 한 번만 퍼뜨린다 (칸마다 따로 풀지 않음).
    """
    idx = PointIndex(g.nodes)
    targets = [e for e in ers if e["tier"] in tiers]
    sources: dict[int, float] = {}
    origin_name: dict[int, str] = {}
    unsnapped_er = []
    for e in targets:
        hit = idx.nearest(e["lat"], e["lon"], snap_m)
        if hit is None:
            unsnapped_er.append(e["name"])
            continue
        node, d = hit
        cost = _snap_cost(d, access_kmh)
        if node not in sources or cost < sources[node]:
            sources[node], origin_name[node] = cost, e["name"]
    cutoff = None if cutoff_min is None else cutoff_min * 60
    reached = multi_source_dijkstra(g.reversed(), sources, cutoff) if sources else {}

    minutes: list[float | None] = []
    nearest: list[str | None] = []
    no_road = 0
    for c in cells:
        hit = idx.nearest(c["lat"], c["lon"], snap_m)
        if hit is None:
            no_road += 1
            minutes.append(None)
            nearest.append(None)
            continue
        node, d = hit
        r = reached.get(node)
        if r is None:
            minutes.append(None)
            nearest.append(None)
            continue
        minutes.append((r[0] + _snap_cost(d, access_kmh)) / 60)
        nearest.append(origin_name[r[1]])
    info = {"targets": len(targets), "targets_unsnapped": unsnapped_er, "cells_no_road": no_road}
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
