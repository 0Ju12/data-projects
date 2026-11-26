"""도로 그래프와 최단 시간 계산."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field


@dataclass
class RoadGraph:
    nodes: dict[int, tuple[float, float]] = field(default_factory=dict)  # id → (위도, 경도)
    adj: dict[int, list[tuple[int, float]]] = field(default_factory=dict)  # id → [(이웃, 초)]

    def add_edge(self, a: int, b: int, seconds: float) -> None:
        self.adj.setdefault(a, []).append((b, seconds))
        self.adj.setdefault(b, [])

    def reversed(self) -> RoadGraph:
        """간선 방향을 뒤집은 그래프. '각 지점 → 가장 가까운 응급실' 을 응급실 쪽에서 한 번에 풀 때 쓴다."""
        g = RoadGraph(nodes=self.nodes)
        for a, outs in self.adj.items():
            g.adj.setdefault(a, [])
            for b, s in outs:
                g.add_edge(b, a, s)
        return g

    def edge_count(self) -> int:
        return sum(len(v) for v in self.adj.values())

    def largest_component(self) -> RoadGraph:
        """방향을 무시하고 이어진 덩어리 중 가장 큰 것만 남긴다.
        등급을 골라 받으면 (예: 주거 도로 제외) 바깥과 끊긴 작은 조각이 생기는데, 칸이 그런 조각에
        붙으면 응급실에 '못 닿음' 으로 잘못 나온다."""
        und: dict[int, list[int]] = {}
        for a, outs in self.adj.items():
            for b, _ in outs:
                und.setdefault(a, []).append(b)
                und.setdefault(b, []).append(a)
        seen: set[int] = set()
        best: list[int] = []
        for start in self.nodes:
            if start in seen:
                continue
            comp, stack = [], [start]
            seen.add(start)
            while stack:
                x = stack.pop()
                comp.append(x)
                for y in und.get(x, ()):
                    if y not in seen:
                        seen.add(y)
                        stack.append(y)
            if len(comp) > len(best):
                best = comp
        keep = set(best)
        g = RoadGraph(nodes={k: self.nodes[k] for k in best})
        for a in best:
            g.adj[a] = [(b, s) for b, s in self.adj.get(a, ()) if b in keep]
        return g


def multi_source_dijkstra(
    g: RoadGraph, sources: dict[int, float], cutoff: float | None = None
) -> dict[int, tuple[float, int]]:
    """여러 출발점에서 동시에 퍼지는 다익스트라.

    sources: 출발 노드 → 시작 비용(초). 응급실이 도로에서 떨어져 있으면 그 접근 시간을 시작 비용으로 준다.
    반환: 노드 → (가장 짧은 시간, 그 시간을 준 출발 노드). cutoff 초를 넘는 노드는 넣지 않는다.
    """
    best: dict[int, tuple[float, int]] = {}
    heap = [(cost, src, src) for src, cost in sources.items()]
    heapq.heapify(heap)
    while heap:
        t, node, origin = heapq.heappop(heap)
        if node in best:
            continue
        if cutoff is not None and t > cutoff:
            break
        best[node] = (t, origin)
        for nbr, s in g.adj.get(node, ()):
            if nbr not in best:
                heapq.heappush(heap, (t + s, nbr, origin))
    return best
