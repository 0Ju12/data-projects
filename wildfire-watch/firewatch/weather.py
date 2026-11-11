"""격자 칸별 일 기상(Open-Meteo, CC BY 4.0)과 Fosberg 화재기상지수(FFWI).

FFWI(Fosberg 1978)는 기온·습도·풍속만으로 '불이 붙으면 얼마나 잘 번질 날씨인가'를 0~100 근처 값으로
나타냅니다. 강수 이력(연료가 얼마나 말랐는지)은 반영하지 않습니다.
여기서는 하루 중 최고기온·최저습도·최대풍속을 함께 넣으므로 실제 같은 시각의 값보다 높게 나오는
'그날 가장 나쁜 조건' 근사입니다.
"""
from __future__ import annotations

import csv
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

from . import grid

API = "https://api.open-meteo.com/v1/forecast"
FIELDS = ["cell", "date", "tmax_c", "rhmin", "wind_kmh", "precip_mm", "ffwi", "kind"]


def emc(rh: float, t_f: float) -> float:
    """평형 함수율(%) — Simard(1968) 식"""
    if rh < 10:
        return 0.03229 + 0.281073 * rh - 0.000578 * rh * t_f
    if rh <= 50:
        return 2.22749 + 0.160107 * rh - 0.01478 * t_f
    return 21.0606 + 0.005565 * rh ** 2 - 0.00035 * rh * t_f - 0.483199 * rh


def ffwi(t_c: float, rh: float, wind_kmh: float) -> float:
    m = emc(max(0.0, min(100.0, rh)), t_c * 9 / 5 + 32) / 30
    eta = 1 - 2 * m + 1.5 * m ** 2 - 0.5 * m ** 3
    u = wind_kmh / 1.609344
    return max(0.0, eta * math.sqrt(1 + u * u) / 0.3002)


def fetch(cells: list[str], past_days: int = 10, forecast_days: int = 3, chunk: int = 50) -> list[dict]:
    rows = []
    for i in range(0, len(cells), chunk):
        part = cells[i:i + chunk]
        cs = [grid.cell_center(c) for c in part]
        q = urllib.parse.urlencode({
            "latitude": ",".join(f"{a:.3f}" for a, _ in cs), "longitude": ",".join(f"{b:.3f}" for _, b in cs),
            "daily": "temperature_2m_max,relative_humidity_2m_min,wind_speed_10m_max,precipitation_sum",
            "past_days": past_days, "forecast_days": forecast_days, "timezone": "Asia/Seoul"})
        with urllib.request.urlopen(urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "firewatch"}), timeout=120) as f:
            data = json.load(f)
        rows += parse(data if isinstance(data, list) else [data], part, forecast_days)
    return rows


def parse(data: list[dict], cells: list[str], forecast_days: int) -> list[dict]:
    """Open-Meteo 응답 → 행. 마지막 forecast_days 일은 예보(forecast), 그 앞은 지난 날(obs)."""
    out = []
    for cell, loc in zip(cells, data):
        d = loc["daily"]
        n = len(d["time"])
        for j, day in enumerate(d["time"]):
            t, rh, w, p = (d["temperature_2m_max"][j], d["relative_humidity_2m_min"][j], d["wind_speed_10m_max"][j], d["precipitation_sum"][j])
            if t is None or rh is None or w is None:
                continue
            out.append({"cell": cell, "date": day, "tmax_c": t, "rhmin": rh, "wind_kmh": w, "precip_mm": 0.0 if p is None else p,
                        "ffwi": round(ffwi(t, rh, w), 1), "kind": "forecast" if j >= n - forecast_days + 1 else "obs"})
    return out


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return [dict(r, ffwi=float(r["ffwi"]), precip_mm=float(r["precip_mm"]), tmax_c=float(r["tmax_c"]),
                     rhmin=float(r["rhmin"]), wind_kmh=float(r["wind_kmh"])) for r in csv.DictReader(f)]


def merge(path: Path, new: list[dict]) -> None:
    """(칸, 날짜)마다 한 줄. 새로 받은 값이 이전 값(특히 예보)을 덮어씀.
    단, 이미 obs 로 저장된 날을 forecast 로 되돌리지는 않음."""
    cur = {(r["cell"], r["date"]): r for r in load(path)}
    for r in new:
        k = (r["cell"], r["date"])
        if k in cur and cur[k]["kind"] == "obs" and r["kind"] == "forecast":
            continue
        cur[k] = r
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows({k: r[k] for k in FIELDS} for _, r in sorted(cur.items()))
