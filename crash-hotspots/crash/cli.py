"""python -m crash.cli build      # data/crashes_*.csv → 핫스팟 → data/summary.json (네트워크 없음)"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from . import hotspot, load

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


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
    kst = datetime.now(timezone.utc) + timedelta(hours=9)
    summary = {
        "built": kst.strftime("%Y-%m-%d %H:%M KST"), "region": cfg["region"], "inputs": reads,
        "crashes": len(points), "cell_m": cfg["cell_m"], "band_m": cfg["band_m"], "fdr_q": cfg["fdr_q"],
        "study_cells": int(mask.sum()), "cells_with_crash": int((g.counts > 0).sum()),
        "hot_cells": int(hot.sum()), "crashes_in_hot_cells": float(g.counts[hot].sum()),
        "zones": len(zs), "top_zones": zs[:30],
        "z_max": None if np.isnan(z).all() else round(float(np.nanmax(z)), 2),
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "build"
    if cmd != "build":
        raise SystemExit(__doc__)
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    print(json.dumps(build(cfg), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
