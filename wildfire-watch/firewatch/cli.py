"""python -m firewatch.cli run        # 받기 → 합치기 → 상시 열원 갱신 → 평가 → docs/data.json
   python -m firewatch.cli build      # 저장된 자료로 평가·페이지 자료만 다시 만들기 (네트워크 없음)"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import evaluate, firms, grid, sources, weather

ROOT = Path(__file__).resolve().parent.parent
DATA, DOCS = ROOT / "data", ROOT / "docs"


def build(status: dict | None = None) -> dict:
    det = firms.load(DATA / "detections.csv")
    known = sources.update(DATA / "static_sources.csv", det)
    wx = weather.load(DATA / "weather.csv")
    for d in det:
        d["static"] = sources.is_static(d, known)
        d["kst"] = evaluate.kst_date(d)
    fires = [d for d in det if not d["static"]]
    days = sorted({d["kst"] for d in det})
    # 양 끝 날은 위성 자료가 하루치를 다 덮지 못하므로 평가에서 뺌
    ev = evaluate.evaluate(wx, fires, days[1], days[-2]) if len(days) >= 3 else None
    today = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")
    wdays = sorted({w["date"] for w in wx})
    by = {}
    for w in wx:
        by.setdefault(w["date"], {})[w["cell"]] = [w["ffwi"], w["tmax_c"], w["rhmin"], w["wind_kmh"], w["precip_mm"]]
    land = set(grid.land_cells())
    summary = {
        "updated": today, "detections": len(det), "static_detections": len(det) - len(fires), "fire_detections": len(fires),
        "fire_detections_on_land": sum(1 for d in fires if grid.cell_id(d["lat"], d["lon"]) in land),
        "static_sources": len(known), "detection_days": [days[0], days[-1]] if days else None, "evaluation": ev, "fetch": status or {},
    }
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    page = {
        "summary": summary, "today": today, "step": grid.STEP, "bbox": grid.BBOX, "outline": [[list(p) for p in r] for r in grid.rings()],
        "cells": grid.land_cells(), "days": wdays, "forecast_from": min((w["date"] for w in wx if w["kind"] == "forecast"), default=None),
        "weather": by,
        # 화재 의심은 한국 육지 칸 안의 것만 표시 (범위에 걸친 북한·해상 탐지는 평가에도 쓰지 않으므로 지도에서도 뺌)
        "detections": [[d["kst"], d["lat"], d["lon"], 1 if d["static"] else 0, d["sat"], d["frp"]] for d in det
                       if d["kst"] in set(wdays) and (d["static"] or grid.cell_id(d["lat"], d["lon"]) in land)],
        "static": [[a, b, n, grid.near_city(a, b)] for (a, b), n in sorted(known.items(), key=lambda kv: -kv[1])],
        "near": {c: grid.near_city(*grid.cell_center(c)) for c in grid.land_cells()},
    }
    DOCS.mkdir(exist_ok=True)
    (DOCS / "data.json").write_text(json.dumps(page, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return summary


def run() -> dict:
    rows, status = firms.fetch()
    status["new"] = firms.merge(DATA / "detections.csv", rows)
    try:
        weather.merge(DATA / "weather.csv", weather.fetch(grid.land_cells()))
        status["weather"] = "ok"
    except Exception as e:                      # 기상을 못 받아도 탐지는 저장하고 끝까지 감
        status["weather"] = f"실패: {type(e).__name__}"
    return build(status)


def main(argv=None) -> int:
    cmd = (argv or sys.argv[1:] or ["run"])[0]
    s = run() if cmd == "run" else build()
    print(json.dumps(s, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
