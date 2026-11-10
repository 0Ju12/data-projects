"""실행: python -m geopipe.cli run [--backfill-from 2023-11-01] [--offline tests/fixtures/usgs_sample.geojson]

1) 지난 실행 시각 3일 전부터(없으면 backfill 시작일부터) 1년 단위로 끊어 수집
2) 기존 CSV 와 합쳐 정제 (수정본 교체, 격리 집계)
3) CSV·SQLite·요약 JSON·대시보드 저장
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from . import analyze, dashboard, fetch, store, transform

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def windows(start: datetime, end: datetime, days: int = 365):
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=days), end)
        yield cur, nxt
        cur = nxt


def run(cfg: dict, data_dir: Path, docs_dir: Path, backfill_from: str | None = None, offline: Path | None = None, now: datetime | None = None) -> dict:
    now = now or fetch.utcnow()
    state = store.load_state(data_dir / "state.json")
    existing = store.load_csv(data_dir / "events.csv")
    if offline:
        features = json.loads(offline.read_text(encoding="utf-8"))["features"]
    else:
        features = []
        last = state.get("last_run_by_region", {})
        for region in [r for r in cfg["regions"] if r.get("collect", True)]:   # 지역마다 자기 최소 규모·시작일로 수집, id 로 합침
            if last.get(region["name"]):
                start = datetime.fromisoformat(last[region["name"]]) - timedelta(days=cfg.get("overlap_days", 3))
            else:
                start = datetime.fromisoformat(backfill_from or region.get("backfill_from") or cfg["backfill_from"])
            for a, b in windows(start, now):
                features += fetch.fetch(region, a, b)
    events, q = transform.clean(features, existing)
    store.save_csv(data_dir / "events.csv", events)
    store.to_sqlite(data_dir / "events.sqlite", events)
    evs = list(events.values())
    # 분석 기간은 지역마다 수집 시작일부터 (다른 지역용으로 더 일찍 받은 이벤트가 섞이지 않게)
    summaries = [analyze.summarize(evs, dict(r, since=r.get("backfill_from") or cfg["backfill_from"])) for r in cfg["regions"]]
    since = (now - timedelta(days=cfg["map_days"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    pts = [[e.time_kst[:16], e.lat, e.lon, e.depth_km, e.mag, e.place] for e in sorted(evs, key=lambda e: e.time_utc) if e.time_utc >= since]
    updated = now.strftime("%Y-%m-%d %H:%M")
    (data_dir / "summary.json").write_text(json.dumps({"updated": updated, "quality": q.__dict__, "regions": summaries}, ensure_ascii=False, indent=1), encoding="utf-8")
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "index.html").write_text(dashboard.render(summaries, q.__dict__, pts, updated, cfg), encoding="utf-8")
    if not offline:
        stamp = now.isoformat(timespec="seconds")
        store.save_state(data_dir / "state.json", {"last_run_by_region": {r["name"]: stamp for r in cfg["regions"] if r.get("collect", True)}, "events": len(events)})
    return {"received": q.received, "kept": q.kept, "regions": {s["region"]: s["n"] for s in summaries}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--docs", default=str(ROOT / "docs"))
    ap.add_argument("--backfill-from")
    ap.add_argument("--offline", help="네트워크 없이 GeoJSON 파일로 실행 (테스트·시연용)")
    a = ap.parse_args(argv)
    out = run(load_config(Path(a.config)), Path(a.data), Path(a.docs), a.backfill_from, Path(a.offline) if a.offline else None)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
