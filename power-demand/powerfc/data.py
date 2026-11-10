"""데이터 적재.

- 전력 수요: 한국전력거래소 '시간별 전국 전력수요량'(공공데이터포털 15065266, 2025년, 단위 MW).
  원본은 하루 한 줄에 1시~24시 열이 있는 넓은 표(CP949) → UTF-8 로 바꿔 data/ 에 두고, 여기서 긴 표로 바꿉니다.
  'N시' 열은 (N-1)시~N시 구간이므로 시작 시각 (N-1)시로 기록합니다.
- 기온: Open-Meteo Historical Weather API (ERA5 재분석, CC BY 4.0). 서울·부산·대전·광주 4개 도시 시간별 기온의 평균.
  키가 필요 없고, 한 번 받은 값은 data/weather_2025.csv 에 저장해 다시 받지 않습니다.
- 공휴일: 2025년 법정공휴일·대체공휴일·임시공휴일 (행정안전부 발표 기준)
"""
from __future__ import annotations

import csv
import json
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

CITIES = {"서울": (37.57, 126.98), "부산": (35.18, 129.08), "대전": (36.35, 127.38), "광주": (35.16, 126.85)}
HOLIDAYS_2025 = {
    "2025-01-01": "신정", "2025-01-27": "임시공휴일", "2025-01-28": "설날 연휴", "2025-01-29": "설날", "2025-01-30": "설날 연휴",
    "2025-03-01": "삼일절", "2025-03-03": "대체공휴일", "2025-05-05": "어린이날·부처님오신날", "2025-05-06": "대체공휴일",
    "2025-06-03": "대통령선거", "2025-06-06": "현충일", "2025-08-15": "광복절", "2025-10-03": "개천절",
    "2025-10-05": "추석 연휴", "2025-10-06": "추석", "2025-10-07": "추석 연휴", "2025-10-08": "대체공휴일", "2025-10-09": "한글날",
    "2025-12-25": "성탄절",
}


def load_demand(path: Path) -> list[tuple[datetime, float]]:
    out = []
    with path.open(encoding="utf-8") as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            if not row or not row[0].strip():
                continue
            d = datetime.strptime(row[0].strip(), "%Y-%m-%d")
            for h, v in enumerate(row[1:25]):
                if v.strip():
                    out.append((d + timedelta(hours=h), float(v)))
    return out


def fetch_weather(start: str, end: str) -> dict[str, list[float]]:
    temps = {}
    for name, (lat, lon) in CITIES.items():
        url = ("https://archive-api.open-meteo.com/v1/archive?"
               f"latitude={lat}&longitude={lon}&start_date={start}&end_date={end}&hourly=temperature_2m&timezone=Asia%2FSeoul")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "power-demand-portfolio"}), timeout=60) as r:
            d = json.loads(r.read())
        temps[name] = d["hourly"]["temperature_2m"]
        temps["time"] = d["hourly"]["time"]
    return temps


def load_weather(path: Path, start="2025-01-01", end="2025-12-31") -> dict[datetime, float]:
    if not path.exists():
        w = fetch_weather(start, end)
        with path.open("w", encoding="utf-8", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["time"] + list(CITIES) + ["mean"])
            for i, t in enumerate(w["time"]):
                vals = [w[c][i] for c in CITIES]
                ok = [v for v in vals if v is not None]
                wr.writerow([t] + vals + [round(sum(ok) / len(ok), 2) if ok else ""])
    out = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["mean"]:
                out[datetime.fromisoformat(row["time"])] = float(row["mean"])
    return out


def is_holiday(d: date) -> bool:
    return d.strftime("%Y-%m-%d") in HOLIDAYS_2025
