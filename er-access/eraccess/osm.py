"""OpenStreetMap 도로를 Overpass 로 받아 이동 시간 그래프로 만든다."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from .geo import haversine_m
from .graph import RoadGraph

# 응답이 불안정해서 차례로 시도한다 (overpass-api.de 는 이 실행 환경에서 연결이 자주 끊겼다)
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# 도로 등급별 차량 평균 속도(km/h). 신호·정체를 감안해 제한속도보다 낮게 잡은 가정값이고 config.json 에서 바꿀 수 있다.
DEFAULT_SPEEDS = {
    "motorway": 90, "trunk": 70, "primary": 50, "secondary": 45, "tertiary": 40,
    "unclassified": 30, "residential": 25, "living_street": 10, "service": 15,
}
ONEWAY_BY_DEFAULT = {"motorway"}


def build_query(bbox: list[float], classes: list[str], timeout: int = 180) -> str:
    """bbox = [남, 서, 북, 동]. 램프(_link) 도 같은 등급으로 포함."""
    pattern = "|".join(classes)
    s, w, n, e = bbox
    return (f'[out:json][timeout:{timeout}];'
            f'way["highway"~"^({pattern})(_link)?$"]({s},{w},{n},{e});'
            f'(._;>;);out body;')


def fetch(query: str, timeout: int = 300) -> dict:
    last = None
    for url in ENDPOINTS:
        try:
            body = urllib.parse.urlencode({"data": query}).encode()
            req = urllib.request.Request(url, data=body, headers={"User-Agent": "data-projects/er-access"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:                  # 다음 미러로
            last = e
    raise RuntimeError(f"Overpass 모든 엔드포인트 실패: {last}")


def _speed(tags: dict, speeds: dict) -> float | None:
    hw = tags.get("highway", "")
    base = speeds.get(hw.removesuffix("_link"))
    if base is None:
        return None
    m = re.match(r"\s*(\d+)", tags.get("maxspeed", ""))
    # 표시된 제한속도가 가정 속도보다 낮을 때만 따른다 (스쿨존 30 등)
    return min(base, float(m.group(1))) if m else float(base)


def _direction(tags: dict) -> int:
    """1: 정방향만, -1: 역방향만, 0: 양방향."""
    ow = tags.get("oneway", "")
    if ow in ("yes", "true", "1"):
        return 1
    if ow == "-1":
        return -1
    if ow == "no":
        return 0
    if tags.get("junction") == "roundabout" or tags.get("highway", "").removesuffix("_link") in ONEWAY_BY_DEFAULT:
        return 1
    return 0


def to_graph(data: dict, speeds: dict | None = None) -> RoadGraph:
    speeds = speeds or DEFAULT_SPEEDS
    coords = {el["id"]: (el["lat"], el["lon"]) for el in data.get("elements", []) if el["type"] == "node"}
    g = RoadGraph()
    for el in data.get("elements", []):
        if el["type"] != "way":
            continue
        tags = el.get("tags", {})
        kmh = _speed(tags, speeds)
        if kmh is None:
            continue
        direction = _direction(tags)
        ids = [i for i in el.get("nodes", []) if i in coords]
        for a, b in zip(ids, ids[1:]):
            sec = haversine_m(*coords[a], *coords[b]) / (kmh / 3.6)
            g.nodes[a], g.nodes[b] = coords[a], coords[b]
            if direction >= 0:
                g.add_edge(a, b, sec)
            if direction <= 0:
                g.add_edge(b, a, sec)
    return g
