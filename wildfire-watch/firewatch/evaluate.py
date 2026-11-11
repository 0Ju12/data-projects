"""지수가 높았던 칸에서 실제로 화재 탐지가 더 많았는지 따져 보기.

단위는 (육지 칸, 날짜). 상시 열원을 뺀 탐지가 하나라도 있으면 양성입니다.
- AUC: 양성 칸-날의 지수가 음성 칸-날보다 높을 확률 (0.5 = 무작위와 같음)
- 상위 20% 적중률: 날마다 지수 상위 20% 칸 안에 그날 양성 칸이 들어간 비율 (무작위면 약 20%)
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from . import grid


def kst_date(d: dict) -> str:
    """FIRMS 의 날짜·시각은 UTC → 기상 자료와 맞추려고 한국 날짜로 바꿈"""
    t = datetime.strptime(f"{d['date']} {str(d['time']).zfill(4)}", "%Y-%m-%d %H%M") + timedelta(hours=9)
    return t.strftime("%Y-%m-%d")


def positives(detections: list[dict]) -> dict[str, set[str]]:
    """날짜 → 탐지가 있는 육지 칸"""
    out = defaultdict(set)
    land = set(grid.land_cells())
    for d in detections:
        c = grid.cell_id(d["lat"], d["lon"])
        if c in land:
            out[kst_date(d)].add(c)
    return out


def auc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    rank_sum, i = 0.0, 0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        r = (i + j + 1) / 2                         # 같은 값은 평균 순위
        rank_sum += r * sum(lab for _, lab in allv[i:j])
        i = j
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def evaluate(weather: list[dict], detections: list[dict], first: str, last: str) -> dict:
    """first~last(한국 날짜, 탐지 자료가 온전히 있는 구간)의 지난 날 자료로 평가"""
    pos_cells = positives(detections)
    by_day = defaultdict(dict)
    for w in weather:
        if w["kind"] == "obs" and first <= w["date"] <= last:
            by_day[w["date"]][w["cell"]] = w["ffwi"]
    pos, neg, hit, tot = [], [], 0, 0
    for day, cells in sorted(by_day.items()):
        ranked = sorted(cells, key=cells.get, reverse=True)
        top = set(ranked[:max(1, round(len(ranked) * 0.2))])
        for c, v in cells.items():
            (pos if c in pos_cells.get(day, ()) else neg).append(v)
        p = [c for c in pos_cells.get(day, ()) if c in cells]
        tot += len(p)
        hit += sum(1 for c in p if c in top)
    a = auc(pos, neg)
    return {"first": first, "last": last, "days": len(by_day), "cell_days": len(pos) + len(neg), "positive_cell_days": len(pos),
            "auc": None if a is None else round(a, 3), "top20_hit": None if not tot else round(hit / tot, 3),
            "mean_ffwi_pos": None if not pos else round(sum(pos) / len(pos), 1), "mean_ffwi_neg": None if not neg else round(sum(neg) / len(neg), 1)}
