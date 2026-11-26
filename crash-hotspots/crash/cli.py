"""python -m crash.cli build      # data/crashes_*.csv (+ data/official_*.csv) → 핫스팟 → data/summary.json, docs/data.json (네트워크 없음)"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from . import hotspot, load, official

ROOT = Path(__file__).resolve().parent.parent
DATA, DOCS = ROOT / "data", ROOT / "docs"


def build(cfg: dict) -> dict:
    files = sorted(ROOT.glob(cfg["inputs"]))
    if not files:
        raise SystemExit(f"{cfg['inputs']} 에 맞는 사고 파일이 없습니다 (README 의 '자료 받기' 참고)")
    points, reads = [], []
    for f in files:
        rows, st = load.load(f)
        points += rows
        reads.append(st)
    g = hotspot.make_grid(points, cfg["cell_m"], cfg.get("weight"))
    mask = hotspot.study_mask(g, cfg["band_m"])
    z = hotspot.gi_star(g, cfg["band_m"], mask)
    hot = hotspot.bh_hot(z, cfg["fdr_q"])
    zs = hotspot.zones(g, hot, z)

    # 핫스팟 칸 안 사고의 구성 (유형·도로 형태) — '어떤 사고가 몰리나'
    def cell_of(p):
        return int((p["y"] - g.y0) // g.cell), int((p["x"] - g.x0) // g.cell)

    in_hot = [p for p in points if hot[cell_of(p)]]
    mix = {
        "kind": Counter(p["kind"] for p in in_hot if p["kind"]).most_common(8),
        "road": Counter(p["road"] for p in in_hot if p["road"]).most_common(8),
    }

    spots, off_reads, cmp = [], [], None
    for f in sorted(ROOT.glob(cfg.get("official", "data/official_*.csv"))):
        rows, st = official.load(f)
        spots += rows
        off_reads.append(st)
    if spots:
        cmp = official.compare(spots, g, hot, cfg.get("compare_near_m", 500))

    kst = datetime.now(timezone.utc) + timedelta(hours=9)
    summary = {
        "built": kst.strftime("%Y-%m-%d %H:%M KST"),
        "region": cfg["region"],
        "inputs": reads,
        "crashes": len(points),
        "cell_m": cfg["cell_m"],
        "band_m": cfg["band_m"],
        "fdr_q": cfg["fdr_q"],
        "study_cells": int(mask.sum()),
        "cells_with_crash": int((g.counts > 0).sum()),
        "hot_cells": int(hot.sum()),
        "crashes_in_hot_cells": float(g.counts[hot].sum()),
        "zones": len(zs),
        "top_zones": zs[:30],
        "hot_mix": mix,
        "official": {"inputs": off_reads, "compare": cmp},
        "z_max": None if np.isnan(z).all() else round(float(np.nanmax(z)), 2),
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    # 지도용: 사고가 난 칸마다 [위도, 경도, 사고 수, z, 핫스팟 여부]
    cells = []
    for i, j in zip(*np.nonzero(g.counts > 0)):
        lat, lon = g.center(i, j)
        zv = z[i, j]
        cells.append(
            [
                round(lat, 5),
                round(lon, 5),
                round(float(g.counts[i, j]), 2),
                None if np.isnan(zv) else round(float(zv), 2),
                1 if hot[i, j] else 0,
            ]
        )
    page = {
        "summary": summary,
        "cells": cells,
        "official": [[s["name"], round(s["lat"], 5), round(s["lon"], 5), s["count"], s["year"]] for s in spots],
    }
    DOCS.mkdir(exist_ok=True)
    (DOCS / "data.json").write_text(json.dumps(page, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return summary


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "build"
    if cmd != "build":
        raise SystemExit(__doc__)
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    s = build(cfg)
    print(json.dumps({k: s[k] for k in ("crashes", "hot_cells", "zones", "z_max")}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
