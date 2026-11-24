"""도로 그래프와 최단 시간 계산."""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field


@dataclass
class RoadGraph:
    nodes: dict[int, tuple[float, float]] = field(default_factory=dict)      # id → (위도, 경도)
    adj: dict[int, list[tuple[int, float]]] = field(default_factory=dict)    # id → [(이웃, 초)]

    def add_edge(self, a: int, b: int, seconds: float) -> None:
        self.adj.setdefault(a, []).append((b, seconds))
        self.adj.setdefault(b, [])

    def reversed(self) -> "RoadGraph":
        """간선 방향을 뒤집은 그래프. '각 지점 → 가장 가까운 응급실' 을 응급실 쪽에서 한 번에 풀 때 쓴다."""
        g = RoadGraph(nodes=self.nodes)
        for a, outs in self.adj.items():
            g.adj.setdefault(a, [])
            for b, s in outs:
                g.add_edge(b, a, s)
        return g

    def edge_count(self) -> int:
        return sum(len(v) for v in self.adj.values())


def multi_source_dijkstra(g: RoadGraph, sources: dict[int, float], cutoff: float | None = None) -> dict[int, tuple[float, int]]:
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
