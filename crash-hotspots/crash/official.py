"""공식 사고 다발 지역(전국교통사고다발지역표준데이터)과 내 핫스팟 대조.

받는 곳: 공공데이터포털 data.go.kr/data/15029185 (도로교통공단, 연간 갱신). 한국에서 내려받아 data/official_*.csv 로.
표준데이터 항목에는 다발지역 중심 위도·경도와 다발지역 폴리곤이 있다고 안내돼 있다. 폴리곤 열의 형식은
받은 뒤 확인해야 해서, GeoJSON 문자열이면 쓰고 아니면 중심점만 쓴다.
"""

from __future__ import annotations

import json
from pathlib import Path

from .load import _num, pick, read_rows
from .utmk import to_utmk

NAME = ["사고지역위치명", "지점명", "사고다발지역명", "spot_nm"]
YEAR = ["사고연도", "기준연도", "searchYearCd"]
COUNT = ["발생건수", "사고건수", "occrrnc_cnt"]
DEATHS = ["사망자수", "dth_dnv_cnt"]
LAT = ["위도", "la_crd", "lat"]
LON = ["경도", "lo_crd", "lon"]
POLY = ["사고다발지역폴리곤정보", "다발지역폴리곤", "폴리곤", "geom_json"]


def _ring(text: str) -> list[tuple[float, float]] | None:
    """GeoJSON Polygon/MultiPolygon 문자열 → 바깥 고리 [(경도, 위도)]. 읽지 못하면 None."""
    try:
        g = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(g, dict):
        return None
    if g.get("type") == "Polygon":
        return [tuple(p[:2]) for p in g["coordinates"][0]]
    if g.get("type") == "MultiPolygon":
        return [tuple(p[:2]) for p in g["coordinates"][0][0]]
    return None


def load(path: Path) -> tuple[list[dict], dict]:
    rows = read_rows(path)
    stats = {"file": Path(path).name, "rows": len(rows), "kept": 0, "with_polygon": 0}
    if not rows:
        return [], stats
    cols = list(rows[0].keys())
    c = {
        k: pick(cols, al)
        for k, al in {
            "name": NAME,
            "year": YEAR,
            "count": COUNT,
            "deaths": DEATHS,
            "lat": LAT,
            "lon": LON,
            "poly": POLY,
        }.items()
    }
    if not (c["lat"] and c["lon"]):
        raise ValueError(f"{path}: 다발지역 중심 좌표(위도·경도) 열이 없음 (있는 열: {cols})")
    out = []
    for r in rows:
        lat, lon = _num(r[c["lat"]]), _num(r[c["lon"]])
        if lat is None or lon is None or not (33.0 <= lat <= 38.7 and 124.5 <= lon <= 132.0):
            continue
        ring = _ring(r.get(c["poly"], "")) if c["poly"] else None
        stats["with_polygon"] += ring is not None
        x, y = to_utmk(lat, lon)
        out.append(
            {
                "name": (r.get(c["name"]) or "").strip() if c["name"] else "",
                "year": (r.get(c["year"]) or "").strip() if c["year"] else "",
                "count": _num(r.get(c["count"])) if c["count"] else None,
                "deaths": _num(r.get(c["deaths"])) if c["deaths"] else None,
                "lat": lat,
                "lon": lon,
                "x": x,
                "y": y,
                "ring": ring,
            }
        )
    stats["kept"] = len(out)
    return out, stats


def compare(spots: list[dict], grid, hot, near_m: float = 500.0) -> dict:
    """두 방향으로 겹침을 센다.
    - 공식 다발 지역 중 내 핫스팟 칸 안(또는 칸 경계에서 near_m 안)에 있는 비율
    - 내 핫스팟 칸 중 공식 다발 지역 중심이 near_m 안에 있는 비율
    공식 다발 지역은 '사망·부상 사고 전체' 기준이고 이 분석은 '사망 사고' 기준이라, 겹침이 낮아도 이상하지 않다."""
    import numpy as np

    hi, hj = np.nonzero(hot)
    centers = [(grid.x0 + (j + 0.5) * grid.cell, grid.y0 + (i + 0.5) * grid.cell) for i, j in zip(hi, hj)]
    half = grid.cell / 2

    def near_hot(x, y):
        return any(abs(x - cx) <= half + near_m and abs(y - cy) <= half + near_m for cx, cy in centers)

    covered = [s for s in spots if near_hot(s["x"], s["y"])]
    hot_with_spot = sum(
        1
        for cx, cy in centers
        if any(abs(s["x"] - cx) <= half + near_m and abs(s["y"] - cy) <= half + near_m for s in spots)
    )
    return {
        "official_spots": len(spots),
        "official_in_hotspots": len(covered),
        "share_official_in_hotspots": round(len(covered) / len(spots), 4) if spots else None,
        "hot_cells": len(centers),
        "hot_cells_with_official": hot_with_spot,
        "share_hot_cells_with_official": round(hot_with_spot / len(centers), 4) if centers else None,
        "near_m": near_m,
    }
