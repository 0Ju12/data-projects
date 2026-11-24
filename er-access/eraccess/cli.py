"""python -m eraccess.cli fetch-pop      # WorldPop 1 km 인구 (해외에서도 받아짐)
   python -m eraccess.cli fetch-roads    # OSM 도로, 타일로 나눠 받기 (끊기면 다시 돌리면 이어 받음)
   python -m eraccess.cli fetch-osm      # OSM 응급실 태그(임시 목록)와 시·읍 이름(지도 표시용)
   python -m eraccess.cli fetch-er       # 공식 응급의료기관 목록 → data/er_list.csv (한국 IP + ER_API_KEY 필요)
   python -m eraccess.cli build          # 받아 둔 자료로 계산만 → data/summary.json, docs/data.json (네트워크 없음)"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import access, er, osm, population
from .geo import PointIndex

ROOT = Path(__file__).resolve().parent.parent
DATA, RAW, DOCS = ROOT / "data", ROOT / "raw", ROOT / "docs"     # raw/ 는 커서 저장소에 넣지 않음 (.gitignore)
POP_ZIP, ROADS_DIR = RAW / "worldpop_kor_2020_1km.zip", RAW / "roads"
ER_CSV, ER_OSM_CSV, PLACES_CSV = DATA / "er_list.csv", DATA / "er_osm.csv", DATA / "places.csv"
CENTERS_CSV = DATA / "regional_centers_wiki.csv"     # 위키백과 권역응급의료센터 표 (공식 목록이 없을 때만)


def config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def fetch_osm(cfg: dict) -> dict:
    rows = er.from_osm(osm.fetch(osm.er_query(cfg["bbox"])))
    er.save(rows, ER_OSM_CSV)
    s, w, n, e = cfg["bbox"]
    q = f'[out:json][timeout:120];node["place"~"^(city|town)$"]({s},{w},{n},{e});out body;'
    places = []
    for el in osm.fetch(q).get("elements", []):
        t = el.get("tags", {})
        name = t.get("name:ko") or t.get("name")
        if name:
            places.append([name, t["place"], round(el["lat"], 5), round(el["lon"], 5)])
    DATA.mkdir(exist_ok=True)
    with open(PLACES_CSV, "w", newline="", encoding="utf-8") as f:
        w_ = csv.writer(f)
        w_.writerow(["name", "place", "lat", "lon"])
        w_.writerows(sorted(places))
    return {"er_osm": len(rows), "places": len(places)}


def load_places() -> list[list]:
    if not PLACES_CSV.exists():
        return []
    with open(PLACES_CSV, encoding="utf-8") as f:
        return [[r["name"], r["place"], float(r["lat"]), float(r["lon"])] for r in csv.DictReader(f)]


def build(cfg: dict) -> dict:
    tiles = sorted(ROADS_DIR.glob("*.json"))
    official = ER_CSV.exists()
    er_files = [ER_CSV] if official else [ER_OSM_CSV, CENTERS_CSV]
    missing = [str(p.relative_to(ROOT)) for p in (POP_ZIP, *er_files) if not p.exists()] + ([] if tiles else ["raw/roads/*.json"])
    if missing:
        raise SystemExit(f"먼저 받아야 할 파일: {missing} (README 의 '자료 받기' 참고)")
    t0 = time.time()
    cells = population.load(POP_ZIP, cfg["bbox"])
    g = osm.graph_from_tiles(tiles, cfg["speeds_kmh"])
    ers = er.load(ER_CSV) if official else er.merge_provisional(er.load(ER_OSM_CSV), er.load(CENTERS_CSV))
    net = access.Network(g, cells, cfg["snap_m"], cfg["access_kmh"])
    t_net = time.time() - t0

    results, per_target = [], []
    for t in cfg["targets"]:
        mins, near, info = net.travel_times(ers, t["tiers"], cfg["cutoff_min"])
        # requires: 이 종별이 목록에 하나도 없으면 계산하지 않는다 (임시 목록엔 지역센터가 없어 "지역센터 이상" 이 권역센터만으로 계산되는 것을 막음)
        available = info["targets"] > 0 and all(any(e["tier"] == r for e in ers) for r in t.get("requires", []))
        results.append({"name": t["name"], "minutes": t["minutes"], "tiers": t["tiers"], "available": available,
                        **(access.coverage(cells, mins, t["minutes"]) if available else {}), **info,
                        "bands": access.bands(cells, mins) if available else None})
        per_target.append((mins, near) if available else (None, None))

    places = load_places()
    pidx = PointIndex({k: (p[2], p[3]) for k, p in enumerate(places)}, cell_deg=0.05)

    def near_place(lat, lon):
        hit = pidx.nearest(lat, lon, 25_000)
        return None if hit is None else places[hit[0]][0]

    # 대상 '응급실 아무 곳' (마지막) 기준으로, 사람이 사는 칸 중 가장 먼 곳
    any_mins, any_near = per_target[-1]
    far = sorted((k for k, c in enumerate(cells) if c["pop"] >= 50 and any_mins and any_mins[k] is not None),
                 key=lambda k: -any_mins[k])[:15]
    far_list = [{"lat": round(cells[k]["lat"], 4), "lon": round(cells[k]["lon"], 4), "pop": round(cells[k]["pop"]),
                 "minutes": round(any_mins[k], 1), "nearest_er": ers[any_near[k]]["name"],
                 "place": near_place(cells[k]["lat"], cells[k]["lon"])} for k in far]

    kst = datetime.now(timezone.utc) + timedelta(hours=9)
    summary = {
        "built": kst.strftime("%Y-%m-%d %H:%M KST"), "region": cfg["region"], "bbox": cfg["bbox"],
        "er_source": "official" if official else "provisional", "er_files": [str(p.relative_to(ROOT)) for p in er_files],
        "er": {"rows": len(ers), "by_tier": {k: sum(e["tier"] == k for e in ers) for k in [*er.TIERS, "other"]}},
        "cells": len(cells), "road_tiles": len(tiles), "graph": {"nodes": len(g.nodes), "edges": g.edge_count()},
        "assumptions": {k: cfg[k] for k in ("road_classes", "speeds_kmh", "snap_m", "access_kmh", "cutoff_min")},
        "targets": results, "farthest_cells": far_list, "seconds": round(time.time() - t0, 1), "seconds_network": round(t_net, 1),
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    # 지도용: 칸마다 [위도, 경도, 인구, 대상별 분…]. 숫자를 줄여 파일 크기를 줄인다.
    rows = []
    for k, c in enumerate(cells):
        mins = [None if m is None or m[k] is None else round(m[k], 1) for m, _ in per_target]
        rows.append([round(c["lat"], 4), round(c["lon"], 4), round(c["pop"]), *mins])
    page = {"summary": summary, "ers": [[e["name"], round(e["lat"], 5), round(e["lon"], 5), e["tier"]] for e in ers],
            "cell_deg": 1 / 120, "cells": rows, "places": [p for p in places if p[1] == "city"]}
    DOCS.mkdir(exist_ok=True)
    (DOCS / "data.json").write_text(json.dumps(page, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return summary


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "build"
    cfg = config()
    if cmd == "fetch-pop":
        print(population.download(POP_ZIP))
    elif cmd == "fetch-roads":
        status = osm.fetch_tiled(cfg["bbox"], cfg["road_classes"], ROADS_DIR, cfg.get("tile_deg", 0.25))
        print(json.dumps(status, ensure_ascii=False))
    elif cmd == "fetch-osm":
        print(json.dumps(fetch_osm(cfg), ensure_ascii=False))
    elif cmd == "fetch-er":
        key = os.environ.get("ER_API_KEY")
        if not key:
            raise SystemExit("환경변수 ER_API_KEY 에 공공데이터포털 인증키(일반 인증키, Decoding)를 넣어 주세요")
        print(f"{ER_CSV}: {er.fetch(key, ER_CSV)}행")
    elif cmd == "build":
        s = build(cfg)
        print(json.dumps({k: s[k] for k in ("er_source", "cells", "graph", "seconds")}, ensure_ascii=False))
        for t in s["targets"]:
            print(t["name"], t.get("share_within"), t.get("population_unreached"))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
