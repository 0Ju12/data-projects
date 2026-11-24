"""OpenStreetMap 도로를 Overpass 로 받아 이동 시간 그래프로 만든다.

넓은 범위는 한 번에 받으면 시간 초과가 나서 타일로 나눠 받는다. 타일마다 필요한 필드만 남긴
압축 JSON(raw/roads/*.json)으로 저장하고, 이미 받은 타일은 건너뛰므로 끊겨도 이어서 받을 수 있다.
"""
from __future__ import annotations

import json
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .geo import haversine_m
from .graph import RoadGraph

# 이 실행 환경에서는 overpass-api.de 연결이 자주 끊기고 mail.ru 미러가 응답했다. 차례로 시도한다.
ENDPOINTS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
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
            f'(._;>;);out body qt;')


def er_query(bbox: list[float]) -> str:
    s, w, n, e = bbox
    return (f'[out:json][timeout:120];'
            f'nwr["amenity"="hospital"]["emergency"="yes"]({s},{w},{n},{e});out center tags;')


def fetch(query: str, timeout: int = 300, tries: int = 2) -> dict:
    last = None
    for attempt in range(tries):
        for url in ENDPOINTS:
            try:
                body = urllib.parse.urlencode({"data": query}).encode()
                req = urllib.request.Request(url, data=body, headers={"User-Agent": "data-projects/er-access"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = json.load(r)
                if "remark" in data and "error" in data["remark"].lower():
                    raise RuntimeError(data["remark"][:200])      # 시간 초과 등은 200 으로 오고 remark 에만 적힘
                return data
            except Exception as e:                  # 다음 미러로
                last = e
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Overpass 모든 엔드포인트 실패: {last}")


def compact(data: dict) -> dict:
    """Overpass 응답에서 그래프에 필요한 것만: 노드 좌표와 (등급, 방향, 제한속도, 노드 목록)."""
    nodes = {str(el["id"]): [el["lat"], el["lon"]] for el in data.get("elements", []) if el["type"] == "node"}
    ways = []
    for el in data.get("elements", []):
        if el["type"] != "way":
            continue
        tags = el.get("tags", {})
        m = re.match(r"\s*(\d+)", tags.get("maxspeed", ""))
        ways.append([tags.get("highway", ""), _direction(tags), int(m.group(1)) if m else None, el.get("nodes", [])])
    return {"nodes": nodes, "ways": ways}


def tiles(bbox: list[float], step: float) -> list[list[float]]:
    s, w, n, e = bbox
    out = []
    for i in range(math.ceil((n - s) / step - 1e-9)):
        for j in range(math.ceil((e - w) / step - 1e-9)):
            ts, tw = s + i * step, w + j * step
            out.append([round(ts, 4), round(tw, 4), round(min(ts + step, n), 4), round(min(tw + step, e), 4)])
    return out


def fetch_tiled(bbox: list[float], classes: list[str], out_dir: Path, step: float = 0.25, log=print) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = tiles(bbox, step)
    status = {"tiles": len(todo), "fetched": 0, "skipped": 0, "failed": []}
    for k, t in enumerate(todo, 1):
        path = out_dir / f"{t[0]:.4f}_{t[1]:.4f}.json"
        if path.exists():
            status["skipped"] += 1
            continue
        t0 = time.time()
        try:
            c = compact(fetch(build_query(t, classes)))
        except Exception as e:
            status["failed"].append([t, str(e)[:120]])
            log(f"[{k}/{len(todo)}] {t} 실패: {e}")
            continue
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(c, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)                                   # 다 쓴 뒤에만 이름을 붙여, 반쯤 쓴 타일이 남지 않게
        status["fetched"] += 1
        log(f"[{k}/{len(todo)}] {t} 노드 {len(c['nodes'])} 도로 {len(c['ways'])} ({time.time() - t0:.0f}s)")
        time.sleep(2)                                       # 공용 서버 예의
    return status


def _speed(hw: str, maxspeed: int | None, speeds: dict) -> float | None:
    base = speeds.get(hw.removesuffix("_link"))
    if base is None:
        return None
    # 표시된 제한속도가 가정 속도보다 낮을 때만 따른다 (스쿨존 30 등)
    return float(min(base, maxspeed)) if maxspeed else float(base)


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


def add_compact(g: RoadGraph, c: dict, speeds: dict, seen_ways: set | None = None) -> None:
    """압축 타일 하나를 그래프에 더한다. 타일 경계에 걸친 도로는 양쪽 타일에 다 들어 있어,
    같은 (노드 목록) 도로는 한 번만 더한다."""
    coords = c["nodes"]
    for hw, direction, maxspeed, ids in c["ways"]:
        kmh = _speed(hw, maxspeed, speeds)
        if kmh is None:
            continue
        if seen_ways is not None:
            key = (ids[0], ids[-1], len(ids)) if ids else None
            if key in seen_ways:
                continue
            seen_ways.add(key)
        pts = [(i, coords.get(str(i))) for i in ids]
        pts = [(i, tuple(p)) for i, p in pts if p]
        for (a, pa), (b, pb) in zip(pts, pts[1:]):
            sec = haversine_m(*pa, *pb) / (kmh / 3.6)
            g.nodes[a], g.nodes[b] = pa, pb
            if direction >= 0:
                g.add_edge(a, b, sec)
            if direction <= 0:
                g.add_edge(b, a, sec)


def to_graph(data: dict, speeds: dict | None = None) -> RoadGraph:
    g = RoadGraph()
    add_compact(g, compact(data), speeds or DEFAULT_SPEEDS)
    return g


def graph_from_tiles(paths: list[Path], speeds: dict | None = None) -> RoadGraph:
    g, seen = RoadGraph(), set()
    for p in paths:
        add_compact(g, json.loads(Path(p).read_text(encoding="utf-8")), speeds or DEFAULT_SPEEDS, seen)
    return g
