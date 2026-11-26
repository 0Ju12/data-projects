"""python -m eraccess.cli fetch-pop      # WorldPop 1 km 인구 (해외에서도 받아짐)
python -m eraccess.cli fetch-roads    # OSM 도로: HOT 한국 전체 내보내기(GeoPackage, 약 380 MB)
python -m eraccess.cli fetch-places   # 시·읍 이름(지도·표 표시용): HOT 내보내기
python -m eraccess.cli fetch-osm      # OSM 응급실 태그(임시 목록), Overpass
python -m eraccess.cli fetch-roads-overpass   # (대안) Overpass 로 타일 나눠 받기 — 공용 서버가 막히면 매우 느림
python -m eraccess.cli fetch-er       # 공식 응급의료기관 목록 → data/er_list.csv (한국 IP + ER_API_KEY 필요)
python -m eraccess.cli collect-beds   # 응급실 실시간 가용 병상 한 번 → data/beds/YYYY-MM.csv 에 이어 붙임 (한국 IP + ER_API_KEY)
python -m eraccess.cli korea-fetch    # 한국에서 한 번에: fetch-er + collect-beds + build
python -m eraccess.cli build          # 받아 둔 자료로 계산만 → data/summary.json, docs/data.json (네트워크 없음)"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import access, er, gpkg, osm, population, region
from .geo import PointIndex

ROOT = Path(__file__).resolve().parent.parent
DATA, RAW, DOCS = ROOT / "data", ROOT / "raw", ROOT / "docs"  # raw/ 는 커서 저장소에 넣지 않음 (.gitignore)
POP_ZIP, ROADS_DIR = RAW / "worldpop_kor_2020_1km.zip", RAW / "roads"
ER_CSV, ER_OSM_CSV, PLACES_CSV = DATA / "er_list.csv", DATA / "er_osm.csv", DATA / "places.csv"
CENTERS_CSV = DATA / "regional_centers_wiki.csv"  # 위키백과 권역응급의료센터 표 (공식 목록이 없을 때만)
EXTRA_CSV = (
    DATA / "er_extra_provisional.csv"
)  # OSM 응급실 표시엔 없지만 응급실로 알려진 곳 (울릉군보건의료원 등, 공식 목록 없을 때만)
ROADS_GPKG = RAW / "hotosm" / "roads.gpkg"
HOT = "https://production-raw-data-api.s3.amazonaws.com/ISO3/KOR"  # HDX 'hotosm_kor_*' 의 원본 위치 (ODbL)


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "data-projects/er-access"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return r.read()


def fetch_roads_hot() -> str:
    zpath = RAW / "hotosm_kor_roads_gpkg.zip"
    if not zpath.exists():
        RAW.mkdir(exist_ok=True)
        zpath.write_bytes(_download(f"{HOT}/roads/hotosm_kor_roads_osm_gpkg.zip"))
    with zipfile.ZipFile(zpath) as z:
        z.extract("roads.gpkg", ROADS_GPKG.parent)
    return str(ROADS_GPKG)


def fetch_places_hot(cfg: dict) -> int:
    """시(city)·읍(town) 이름. 지도 글자와 '가장 먼 곳' 표의 위치 설명에만 쓴다."""
    s, w, n, e = cfg["bbox"]
    raw = _download(f"{HOT}/populated_places/hotosm_kor_populated_places_osm_geojson.zip")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = next(x for x in z.namelist() if x.endswith(".geojson"))
        fc = json.loads(z.read(name))
    places = []
    for f in fc["features"]:
        pr, geom = f.get("properties", {}), f.get("geometry") or {}
        if pr.get("place") not in ("city", "town") or geom.get("type") != "Point":
            continue
        lon, lat = geom["coordinates"][:2]
        label = pr.get("name_ko") or pr.get("name:ko") or pr.get("name")
        if label and s <= lat <= n and w <= lon <= e:
            places.append([label, pr["place"], round(lat, 5), round(lon, 5)])
    DATA.mkdir(exist_ok=True)
    with open(PLACES_CSV, "w", newline="", encoding="utf-8") as f:
        w_ = csv.writer(f)
        w_.writerow(["name", "place", "lat", "lon"])
        w_.writerows(sorted(places))
    return len(places)


def config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def fetch_osm(cfg: dict) -> dict:
    rows = er.from_osm(osm.fetch(osm.er_query(cfg["bbox"])))
    er.save(rows, ER_OSM_CSV)
    return {"er_osm": len(rows)}


def load_places() -> list[list]:
    if not PLACES_CSV.exists():
        return []
    with open(PLACES_CSV, encoding="utf-8") as f:
        return [[r["name"], r["place"], float(r["lat"]), float(r["lon"])] for r in csv.DictReader(f)]


def build(cfg: dict) -> dict:
    tiles = sorted(ROADS_DIR.glob("*.json"))
    official = ER_CSV.exists()
    er_files = [ER_CSV] if official else [ER_OSM_CSV, CENTERS_CSV, EXTRA_CSV]
    has_roads = ROADS_GPKG.exists() or tiles
    missing = [str(p.relative_to(ROOT)) for p in (POP_ZIP, *er_files) if not p.exists()] + (
        [] if has_roads else ["raw/hotosm/roads.gpkg"]
    )
    if missing:
        raise SystemExit(f"먼저 받아야 할 파일: {missing} (README 의 '자료 받기' 참고)")
    t0 = time.time()
    cells_all = population.load(POP_ZIP, cfg["bbox"])
    compact = None
    if ROADS_GPKG.exists():
        road_source = "hotosm_gpkg"
        compact = gpkg.read(ROADS_GPKG, cfg["bbox"], cfg["road_classes"])
        g = osm.RoadGraph()
        osm.add_compact(g, compact, cfg["speeds_kmh"])
    else:
        road_source = "overpass_tiles"
        g = osm.graph_from_tiles(tiles, cfg["speeds_kmh"])
    nodes_all = len(g.nodes)
    g = g.largest_component()
    ers = (
        er.load(ER_CSV)
        if official
        else er.merge_provisional(er.load(ER_OSM_CSV) + er.load(EXTRA_CSV), er.load(CENTERS_CSV))
    )
    # 경로는 경계 상자 전체(이웃 시도의 도로·응급실 포함)로 풀고, 집계·지도는 경북 칸만
    net = access.Network(g, cells_all, cfg["snap_m"], cfg["access_kmh"])
    if compact is not None:
        node_reg = region.node_regions(compact)
        sigun_all = []
        for c, hit in zip(cells_all, net.snapped):
            if hit is None:  # 도로에서 먼 산지 칸: 8 km 안 가장 가까운 도로의 시군
                hit = net.idx.nearest(c["lat"], c["lon"], 8_000)
            sigun_all.append(node_reg.get(hit[0]) if hit else None)
    else:
        sigun_all = [cfg["region"]] * len(cells_all)  # 행정구역 정보가 없으면 상자 전체
    keep = [k for k, sg in enumerate(sigun_all) if sg]
    cells = [cells_all[k] for k in keep]
    sigun = [sigun_all[k] for k in keep]
    t_net = time.time() - t0

    # 섬(울릉군): 육지 도로망과 이어지지 않으므로 섬 도로만으로 따로 풀고, 섬 밖 응급실은 '못 닿음'
    islands = []
    for isl in cfg.get("islands", []) if compact is not None else []:
        ic = population.load(POP_ZIP, isl["bbox"])
        ig = osm.RoadGraph()
        osm.add_compact(ig, gpkg.read(ROADS_GPKG, isl["bbox"], isl["road_classes"]), cfg["speeds_kmh"])
        inet = access.Network(ig.largest_component(), ic, cfg["snap_m"], cfg["access_kmh"])
        s_, w_, n_, e_ = isl["bbox"]
        local = [k for k, x in enumerate(ers) if s_ <= x["lat"] <= n_ and w_ <= x["lon"] <= e_]
        per = []
        for t in cfg["targets"]:
            m, nr, _ = inet.travel_times([ers[k] for k in local], t["tiers"], cfg["cutoff_min"])
            per.append((m, [None if j is None else local[j] for j in nr]))
        islands.append({"name": isl["name"], "cells": ic, "per": per})
        cells += ic
        sigun += [isl["name"]] * len(ic)

    results, per_target = [], []
    for ti, t in enumerate(cfg["targets"]):
        mins_all, near_all, info = net.travel_times(ers, t["tiers"], cfg["cutoff_min"])
        # requires: 이 종별이 목록에 하나도 없으면 계산하지 않는다 (임시 목록엔 지역센터가 없어 "지역센터 이상" 이 권역센터만으로 계산되는 것을 막음)
        available = info["targets"] > 0 and all(any(e["tier"] == r for e in ers) for r in t.get("requires", []))
        mins = [mins_all[k] for k in keep] + [m for isl in islands for m in isl["per"][ti][0]]
        near = [near_all[k] for k in keep] + [j for isl in islands for j in isl["per"][ti][1]]
        info["cells_no_road"] = sum(net.snapped[k] is None for k in keep)
        results.append(
            {
                "name": t["name"],
                "minutes": t["minutes"],
                "tiers": t["tiers"],
                "available": available,
                **(access.coverage(cells, mins, t["minutes"]) if available else {}),
                **info,
                "bands": access.bands(cells, mins) if available else None,
            }
        )
        per_target.append((mins, near) if available else (None, None))

    # 시군별: 인구, 대상별 기준 시간 안 비율, 인구 가중 중앙값(분)
    by_sigun = []
    for name in sorted(set(sigun)):
        idx = [k for k, sg in enumerate(sigun) if sg == name]
        sub = [cells[k] for k in idx]
        row = {"name": name, "population": round(sum(c["pop"] for c in sub)), "cells": len(idx)}
        for t, (mins, _) in zip(cfg["targets"], per_target):
            if mins is None:
                continue
            m = [mins[k] for k in idx]
            row[t["name"]] = {
                "share_within": access.coverage(sub, m, t["minutes"])["share_within"],
                "median_min": access.weighted_median(sub, m),
            }
        row["vulnerable"] = access.vulnerable(row, cfg["targets"], cfg.get("vulnerable_share", 0.27))
        by_sigun.append(row)

    places = load_places()
    pidx = PointIndex({k: (p[2], p[3]) for k, p in enumerate(places)}, cell_deg=0.05)

    def near_place(lat, lon):
        hit = pidx.nearest(lat, lon, 25_000)
        return None if hit is None else places[hit[0]][0]

    # 대상 '응급실 아무 곳' (마지막) 기준으로, 사람이 사는 칸 중 가장 먼 곳
    any_mins, any_near = per_target[-1]
    # 같은 면의 칸이 표를 다 채우지 않게, (시군, 읍면)마다 가장 먼 칸 하나만
    best: dict[tuple, int] = {}
    for k, c in enumerate(cells):
        if c["pop"] < 50 or not any_mins or any_mins[k] is None:
            continue
        key = (sigun[k], near_place(c["lat"], c["lon"]))
        if key not in best or any_mins[k] > any_mins[best[key]]:
            best[key] = k
    far = sorted(best.values(), key=lambda k: -any_mins[k])[:15]
    far_list = [
        {
            "lat": round(cells[k]["lat"], 4),
            "lon": round(cells[k]["lon"], 4),
            "pop": round(cells[k]["pop"]),
            "minutes": round(any_mins[k], 1),
            "nearest_er": ers[any_near[k]]["name"],
            "sigun": sigun[k],
            "place": near_place(cells[k]["lat"], cells[k]["lon"]),
        }
        for k in far
    ]

    kst = datetime.now(timezone.utc) + timedelta(hours=9)
    summary = {
        "built": kst.strftime("%Y-%m-%d %H:%M KST"),
        "region": cfg["region"],
        "bbox": cfg["bbox"],
        "er_source": "official" if official else "provisional",
        "er_files": [str(p.relative_to(ROOT)) for p in er_files],
        "er": {"rows": len(ers), "by_tier": {k: sum(e["tier"] == k for e in ers) for k in [*er.TIERS, "other"]}},
        "cells": len(cells),
        "cells_bbox": len(cells_all),
        "road_source": road_source,
        "graph": {"nodes": len(g.nodes), "edges": g.edge_count(), "nodes_before_largest_component": nodes_all},
        "assumptions": {k: cfg[k] for k in ("road_classes", "speeds_kmh", "snap_m", "access_kmh", "cutoff_min")},
        "targets": results,
        "by_sigun": by_sigun,
        "farthest_cells": far_list,
        "seconds": round(time.time() - t0, 1),
        "seconds_network": round(t_net, 1),
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    # 지도용: 칸마다 [위도, 경도, 인구, 시군 번호, 대상별 분…]. 숫자를 줄여 파일 크기를 줄인다.
    names = [r["name"] for r in by_sigun]
    rows = []
    for k, c in enumerate(cells):
        mins = [None if m is None or m[k] is None else round(m[k], 1) for m, _ in per_target]
        rows.append([round(c["lat"], 4), round(c["lon"], 4), round(c["pop"]), names.index(sigun[k]), *mins])
    page = {
        "summary": summary,
        "sigun": names,
        "ers": [[e["name"], round(e["lat"], 5), round(e["lon"], 5), e["tier"]] for e in ers],
        "cell_deg": 1 / 120,
        "cells": rows,
        "places": [p for p in places if p[1] == "city"],
    }
    DOCS.mkdir(exist_ok=True)
    (DOCS / "data.json").write_text(json.dumps(page, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # 가까운 응급실 찾기(er-finder)용: 칸마다 대상별 [분, 가장 가까운 응급실 번호]
    finder = finder_page(cells, per_target, ers, cfg["targets"], summary)
    (DOCS / "finder.json").write_text(json.dumps(finder, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return summary


def finder_page(cells: list[dict], per_target: list, ers: list[dict], targets: list[dict], summary: dict) -> dict:
    """칸 [위도, 경도, 대상1 분, 대상1 응급실 번호, 대상2 분, …]. 계산하지 않은 대상(available=False)은 열에서 뺀다."""
    used = [(t, pt) for t, pt in zip(targets, per_target) if pt[0] is not None]
    rows = []
    for k, c in enumerate(cells):
        row = [round(c["lat"], 4), round(c["lon"], 4)]
        for _, (mins, near) in used:
            row += [None if mins[k] is None else round(mins[k], 1), near[k]]
        rows.append(row)
    return {
        "built": summary.get("built"),
        "er_source": summary.get("er_source"),
        "cell_deg": 1 / 120,
        "targets": [{"name": t["name"], "tiers": t["tiers"]} for t, _ in used],
        "ers": [[e["name"], round(e["lat"], 5), round(e["lon"], 5), e["tier"]] for e in ers],
        "cells": rows,
    }


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "build"
    cfg = config()
    if cmd == "fetch-pop":
        print(population.download(POP_ZIP))
    elif cmd == "fetch-roads":
        print(fetch_roads_hot())
    elif cmd == "fetch-places":
        print(f"{PLACES_CSV}: {fetch_places_hot(cfg)}곳")
    elif cmd == "fetch-roads-overpass":
        status = osm.fetch_tiled(cfg["bbox"], cfg["road_classes"], ROADS_DIR, cfg.get("tile_deg", 0.25))
        print(json.dumps(status, ensure_ascii=False))
    elif cmd == "fetch-osm":
        print(json.dumps(fetch_osm(cfg), ensure_ascii=False))
    elif cmd in ("fetch-er", "collect-beds", "korea-fetch"):
        key = os.environ.get("ER_API_KEY")
        if not key:
            raise SystemExit("환경변수 ER_API_KEY 에 공공데이터포털 인증키(일반 인증키, Decoding)를 넣어 주세요")
        if cmd in ("fetch-er", "korea-fetch"):
            print(f"{ER_CSV}: {er.fetch(key, ER_CSV)}행")
        if cmd in ("collect-beds", "korea-fetch"):
            kst = datetime.now(timezone.utc) + timedelta(hours=9)
            out = DATA / "beds" / f"{kst:%Y-%m}.csv"
            print(f"{out}: {er.fetch_beds(key, out, when=kst.strftime('%Y-%m-%d %H:%M'))}행 추가")
        if cmd == "korea-fetch":
            s = build(cfg)
            print(json.dumps({k: s[k] for k in ("er_source", "er", "cells")}, ensure_ascii=False))
    elif cmd == "build":
        s = build(cfg)
        print(json.dumps({k: s[k] for k in ("er_source", "cells", "graph", "seconds")}, ensure_ascii=False))
        for t in s["targets"]:
            print(t["name"], t.get("share_within"), t.get("population_unreached"))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
