"""NASA FIRMS 활성 화재 탐지 (VIIRS 375 m, 최근 7일 CSV — 키 없이 받을 수 있는 공개 파일).

같은 탐지는 (위성, 날짜, 시각, 위·경도)로 구분해 여러 번 받아도 한 번만 저장합니다.
"""
from __future__ import annotations

import csv
import io
import urllib.request
from pathlib import Path

from . import grid

BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire"
SOURCES = {
    "N20": f"{BASE}/noaa-20-viirs-c2/csv/J1_VIIRS_C2_Russia_Asia_7d.csv",
    "N21": f"{BASE}/noaa-21-viirs-c2/csv/J2_VIIRS_C2_Russia_Asia_7d.csv",
    "SNPP": f"{BASE}/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Russia_Asia_7d.csv",
}
FIELDS = ["sat", "date", "time", "lat", "lon", "frp", "confidence", "daynight"]


def parse(text: str, sat: str) -> list[dict]:
    """FIRMS CSV 본문 → 한국 범위 탐지 목록. 신뢰도 low 는 뺍니다."""
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except (KeyError, ValueError):
            continue
        if not grid.in_bbox(lat, lon) or r.get("confidence", "").strip().lower() in ("low", "l"):
            continue
        out.append({"sat": sat, "date": r["acq_date"], "time": r["acq_time"].zfill(4), "lat": round(lat, 5), "lon": round(lon, 5),
                    "frp": r.get("frp", ""), "confidence": r.get("confidence", ""), "daynight": r.get("daynight", "")})
    return out


def fetch() -> tuple[list[dict], dict]:
    rows, status = [], {}
    for sat, url in SOURCES.items():
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "firewatch"}), timeout=120) as f:
                got = parse(f.read().decode("utf-8", "replace"), sat)
            rows += got
            status[sat] = len(got)
        except Exception as e:                      # 한 위성 파일이 안 받아져도 나머지는 계속
            status[sat] = f"실패: {type(e).__name__}"
    return rows, status


def key(r: dict) -> tuple:
    return (r["sat"], r["date"], str(r["time"]).zfill(4), f"{float(r['lat']):.5f}", f"{float(r['lon']):.5f}")


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return [dict(r, lat=float(r["lat"]), lon=float(r["lon"])) for r in csv.DictReader(f)]


def merge(path: Path, new: list[dict]) -> int:
    """새 탐지를 합쳐 저장하고 새로 들어간 건수를 돌려줌 (여러 번 실행해도 결과가 같음)"""
    old = load(path)
    seen = {key(r) for r in old}
    added = [r for r in new if key(r) not in seen and not seen.add(key(r))]
    rows = sorted(old + added, key=key)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in FIELDS} for r in rows)
    return len(added)
