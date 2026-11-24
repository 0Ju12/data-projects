"""python -m eraccess.cli fetch-pop     # WorldPop 1 km 인구 (해외에서도 받아짐)
   python -m eraccess.cli fetch-roads   # OSM 도로 (Overpass)
   python -m eraccess.cli fetch-er      # 응급의료기관 목록 → data/er_list.csv (한국 IP + ER_API_KEY 필요)
   python -m eraccess.cli build         # 받아 둔 자료로 계산만 → data/summary.json (네트워크 없음)"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import access, er, osm, population

ROOT = Path(__file__).resolve().parent.parent
DATA, RAW = ROOT / "data", ROOT / "raw"           # raw/ 는 커서 저장소에 넣지 않음 (.gitignore)
POP_ZIP, ROADS_JSON, ER_CSV = RAW / "worldpop_kor_2020_1km.zip", RAW / "roads.json", DATA / "er_list.csv"


def config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def build(cfg: dict) -> dict:
    missing = [p.name for p in (POP_ZIP, ROADS_JSON, ER_CSV) if not p.exists()]
    if missing:
        raise SystemExit(f"먼저 받아야 할 파일: {missing} (README 의 '자료 받기' 참고)")
    cells = population.load(POP_ZIP, cfg["bbox"])
    g = osm.to_graph(json.loads(ROADS_JSON.read_text(encoding="utf-8")), cfg["speeds_kmh"])
    ers = er.load(ER_CSV)
    results = []
    for t in cfg["targets"]:
        mins, _, info = access.travel_times(g, cells, ers, t["tiers"], cfg["snap_m"], cfg["access_kmh"], cfg["cutoff_min"])
        results.append({"name": t["name"], **access.coverage(cells, mins, t["minutes"]), **info})
    kst = datetime.now(timezone.utc) + timedelta(hours=9)
    summary = {
        "built": kst.strftime("%Y-%m-%d %H:%M KST"), "region": cfg["region"], "bbox": cfg["bbox"],
        "cells": len(cells), "graph": {"nodes": len(g.nodes), "edges": g.edge_count()},
        "er": {"rows": len(ers), "by_tier": {k: sum(e["tier"] == k for e in ers) for k in [*er.TIERS, "other"]}},
        "targets": results,
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "build"
    cfg = config()
    if cmd == "fetch-pop":
        print(population.download(POP_ZIP))
    elif cmd == "fetch-roads":
        data = osm.fetch(osm.build_query(cfg["bbox"], cfg["road_classes"]))
        RAW.mkdir(exist_ok=True)
        ROADS_JSON.write_text(json.dumps(data), encoding="utf-8")
        print(f"{ROADS_JSON}: 요소 {len(data.get('elements', []))}개")
    elif cmd == "fetch-er":
        key = os.environ.get("ER_API_KEY")
        if not key:
            raise SystemExit("환경변수 ER_API_KEY 에 공공데이터포털 인증키(일반 인증키, Decoding)를 넣어 주세요")
        print(f"{ER_CSV}: {er.fetch(key, ER_CSV)}행")
    elif cmd == "build":
        print(json.dumps(build(cfg), ensure_ascii=False, indent=1))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
