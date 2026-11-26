"""저장소의 세 프로젝트 산출물을 읽어 docs/korea.pmtiles 와 docs/layers.json 을 만든다.

    python -m tiles.build            # 저장소 루트 기준 경로 사용

레이어 (줌 범위) — 모두 최대 줌(11)까지 넣는다. 한 소스의 레이어가 높은 줌 타일에 없으면 MapLibre 가 확대 시 그 레이어를 지워 버림
- quakes        지진 진앙 (3–11)          geo-data-pipeline/data/events.csv
- fire_grid     오늘 화재기상지수 0.25° 칸 (4–11)    wildfire-watch/docs/data.json
- fire_points   최근 7일 위성 화재 탐지 (5–11)
- er_cells      1 km 칸 응급실까지 이동 시간·인구 (6–11, 6·7 은 4×4·2×2 칸을 합쳐 가볍게)  er-access/docs/data.json
- er_sites      응급실 위치 (5–11)
"""

from __future__ import annotations

import csv
import json
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from . import pmtiles
from .tiling import TileSet

ROOT = Path(__file__).resolve().parents[2]
DOCS = Path(__file__).resolve().parents[1] / "docs"
ATTR = "지진 USGS · 산불 NASA FIRMS, Open-Meteo · 도로 © OpenStreetMap (HOT) · 인구 GHSL"
ER_TARGETS = [
    "m_center",
    "m_regional",
    "m_any",
]  # er-access data.json 칸 열 순서 (지역센터 이상, 권역센터, 아무 응급실)


def load_quakes(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("lat") and r.get("mag")]


def add_quakes(ts: TileSet, rows: list[dict], zooms=range(3, 12)) -> None:
    rows = sorted(rows, key=lambda r: float(r["mag"]))  # 큰 지진이 위에 그려지게 나중에
    for z in zooms:
        for k, r in enumerate(rows):
            ts.add_point(
                "quakes",
                z,
                float(r["lon"]),
                float(r["lat"]),
                {
                    "mag": float(r["mag"]),
                    "depth": float(r["depth_km"] or 0),
                    "time": r["time_kst"][:16],
                    "place": r["place"],
                    "year": int(r["time_kst"][:4]),
                },
                fid=k + 1,
            )


def add_fire(ts: TileSet, d: dict, grid_zooms=range(4, 12), point_zooms=range(5, 12), days_back=7) -> dict:
    day = d.get("today") or d["days"][-1]
    wx = d["weather"].get(day) or {}
    step = d["step"]
    for z in grid_zooms:
        for key, v in wx.items():
            lat, lon = map(float, key.split("_"))
            ts.add_box(
                "fire_grid",
                z,
                lon - step / 2,
                lat - step / 2,
                lon + step / 2,
                lat + step / 2,
                {"ffwi": v[0], "tmax": v[1], "rh": v[2], "wind": v[3], "rain": v[4], "near": d["near"].get(key, "")},
            )
    since = (date.fromisoformat(day) - timedelta(days=days_back - 1)).isoformat()
    det = [x for x in d["detections"] if since <= x[0] <= day]
    for z in point_zooms:
        for x in det:
            ts.add_point("fire_points", z, x[2], x[1], {"day": x[0], "static": bool(x[3]), "frp": float(x[5] or 0)})
    return {"day": day, "grid_cells": len(wx), "detections": len(det), "since": since}


def _aggregate(cells: list, deg: float, f: int) -> list[tuple]:
    """칸을 정수 격자 번호에 맞춰 (남, 서, 크기, 인구, [분…]) 로. f×f 칸을 하나로 합칠 때 인구는 합, 분은 인구 가중 평균.

    data.json 의 칸 중심은 소수 4자리로 반올림돼 있어 '중심 ± 반 칸' 으로 그리면 이웃 칸 사이에 1/8 px 틈이 생기고,
    그 틈이 화소 중심에 걸리는 줄마다 흰 선이 보인다 → 중심을 격자 번호로 되돌려 이웃 칸이 같은 경계값을 쓰게 함."""
    groups = defaultdict(list)
    for c in cells:
        groups[(round(c[0] / deg - 0.5) // f, round(c[1] / deg - 0.5) // f)].append(c)
    big = deg * f
    out = []
    for (i, j), g in groups.items():
        pop = sum(c[2] for c in g)
        mins = []
        for t in range(3):
            vals = [(c[4 + t], c[2]) for c in g if c[4 + t] is not None]
            if not vals:
                mins.append(None)
                continue
            w = sum(p for _, p in vals)
            mins.append(
                round(sum(m * p for m, p in vals) / w, 1) if w else round(sum(m for m, _ in vals) / len(vals), 1)
            )
        out.append((i * big, j * big, big, pop, mins))
    return out


def add_er(ts: TileSet, d: dict, cell_zooms=range(6, 12), site_zooms=range(5, 12)) -> dict:
    deg = d["cell_deg"]
    sigun = d["sigun"]
    for z in cell_zooms:
        f = 1 << max(0, 8 - z)
        rows = _aggregate(d["cells"], deg, f)
        for s, w, size, pop, mins in rows:
            props = {"pop": round(pop), **{k: m for k, m in zip(ER_TARGETS, mins)}}
            ts.add_box("er_cells", z, w, s, w + size, s + size, props)
    for z in site_zooms:
        for name, lat, lon, tier in d["ers"]:
            ts.add_point("er_sites", z, lon, lat, {"name": name, "tier": tier})
    return {
        "cells": len(d["cells"]),
        "sites": len(d["ers"]),
        "sigun": len(sigun),
        "built": d["summary"].get("built"),
        "er_source": d["summary"].get("er_source"),
        "targets": [
            {
                "key": k,
                "name": t.get("name"),
                "minutes": t.get("minutes"),
                "cells_with_value": sum(c[4 + i] is not None for c in d["cells"]),
            }
            for i, (k, t) in enumerate(zip(ER_TARGETS, d["summary"]["targets"]))
        ],
    }


LAYER_FIELDS = {
    "quakes": {"mag": "Number", "depth": "Number", "time": "String", "place": "String", "year": "Number"},
    "fire_grid": {
        "ffwi": "Number",
        "tmax": "Number",
        "rh": "Number",
        "wind": "Number",
        "rain": "Number",
        "near": "String",
    },
    "fire_points": {"day": "String", "static": "Boolean", "frp": "Number"},
    "er_cells": {"pop": "Number", "m_center": "Number", "m_regional": "Number", "m_any": "Number"},
    "er_sites": {"name": "String", "tier": "String"},
}


def build(root: Path = ROOT, out: Path = DOCS) -> dict:
    t0 = time.time()
    ts = TileSet()
    info: dict = {}
    quakes = load_quakes(root / "geo-data-pipeline/data/events.csv")
    if quakes:
        add_quakes(ts, quakes)
        info["quakes"] = {"events": len(quakes), "last": max(r["time_kst"] for r in quakes)[:16]}
    fire = root / "wildfire-watch/docs/data.json"
    if fire.exists():
        info["fire"] = add_fire(ts, json.loads(fire.read_text(encoding="utf-8")))
    er = root / "er-access/docs/data.json"
    if er.exists():
        info["er"] = add_er(ts, json.loads(er.read_text(encoding="utf-8")))
    if not ts.tiles:
        raise SystemExit("타일로 만들 자료가 없습니다 (세 프로젝트 산출물이 모두 없음)")
    encoded = ts.encode()
    present = {name for layers in ts.tiles.values() for name in layers}
    zr = defaultdict(list)
    for (z, _, _), layers in ts.tiles.items():
        for name in layers:
            zr[name].append(z)
    meta = {
        "name": "korea-public-data",
        "format": "pbf",
        "attribution": ATTR,
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "vector_layers": [
            {"id": k, "fields": v, "minzoom": min(zr[k]), "maxzoom": max(zr[k])}
            for k, v in LAYER_FIELDS.items()
            if k in present
        ],
        "sources": info,
    }
    out.mkdir(parents=True, exist_ok=True)
    stats = pmtiles.write(
        out / "korea.pmtiles", encoded, meta, bounds=(124.0, 30.0, 132.0, 39.5), center=(128.2, 36.2, 6)
    )
    stats["seconds"] = round(time.time() - t0, 1)
    sizes = defaultdict(int)
    for k, v in encoded.items():
        sizes[k[0]] += len(v)
    stats["raw_bytes_by_zoom"] = dict(sorted(sizes.items()))
    (out / "layers.json").write_text(
        json.dumps(
            {"generated": meta["generated"], "stats": stats, "sources": info, "vector_layers": meta["vector_layers"]},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return stats


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=1))
