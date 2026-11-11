"""형제 프로젝트의 산출물을 읽기 전용 SQLite 하나로 모읍니다.

    python -m dataagent.build_db            # data/agent.sqlite

같은 입력이면 같은 DB 가 나옵니다(매번 새로 만듦). DART 마트는 인증키로 만든 DB 가 저장소에 없어 넣지 않았습니다.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
DB = ROOT / "data" / "agent.sqlite"

CATALOG = {
    "earthquakes": ("USGS 지진 목록 (동아시아, 규모 4 이상). geo-data-pipeline 이 매일 갱신.",
                    {"id": "USGS 이벤트 id", "time_kst": "발생 시각 (한국 시간, 'YYYY-MM-DD HH:MM:SS')", "lat": "위도", "lon": "경도",
                     "depth_km": "깊이 km", "mag": "규모", "mag_type": "규모 종류 (mb, mww …)", "place": "위치 설명 (영문)"}),
    "power_hourly": ("2025-10-01 ~ 12-31 전국 시간별 전력 수요와 하루 전 예측 (시험 구간). power-demand 결과.",
                     {"ts": "시작 시각 'YYYY-MM-DD HH:00'", "date": "날짜", "hour": "0~23", "actual_mw": "실제 수요 MW",
                      "pred_ensemble_mw": "앙상블 예측 MW", "pred_linear_mw": "선형 예측 MW", "pred_gbm_mw": "GBM(+기온) 예측 MW",
                      "pred_naive_mw": "지난주 같은 시각 MW", "temp_c": "4개 도시 평균 기온 ℃", "is_holiday": "휴일(주말 제외 공휴일)이면 1"}),
    "fire_detections": ("NASA FIRMS VIIRS 열 탐지 (한국 범위). wildfire-watch 가 매일 갱신.",
                        {"sat": "위성 (N20, N21, SNPP)", "date_kst": "한국 날짜", "lat": "위도", "lon": "경도", "frp": "화재 복사 에너지 MW",
                         "is_static": "제철소 등 상시 열원으로 판정되면 1", "cell": "0.25° 칸 id", "near": "가까운 도시"}),
    "fire_weather": ("0.25° 육지 칸별 일 기상과 화재기상지수(FFWI). wildfire-watch 결과.",
                     {"cell": "칸 id", "near": "가까운 도시", "date": "날짜", "tmax_c": "최고기온 ℃", "rhmin": "최저 습도 %",
                      "wind_kmh": "최대 풍속 km/h", "precip_mm": "강수 mm", "ffwi": "화재기상지수", "kind": "obs(지난 날) | forecast(예보)"}),
}


def _fire_rows():
    sys.path.insert(0, str(REPO / "wildfire-watch"))
    from firewatch import evaluate, firms, grid, sources, weather   # 판정 규칙을 한 곳에서만 관리
    data = REPO / "wildfire-watch" / "data"
    det = firms.load(data / "detections.csv")
    known = sources.load(data / "static_sources.csv")
    d_rows = [(d["sat"], evaluate.kst_date(d), d["lat"], d["lon"], float(d["frp"] or 0), int(sources.is_static(d, known)),
               grid.cell_id(d["lat"], d["lon"]), grid.near_city(d["lat"], d["lon"])) for d in det]
    w_rows = [(w["cell"], grid.near_city(*grid.cell_center(w["cell"])), w["date"], w["tmax_c"], w["rhmin"], w["wind_kmh"], w["precip_mm"], w["ffwi"], w["kind"])
              for w in weather.load(data / "weather.csv")]
    return d_rows, w_rows


def build(db: Path = DB) -> dict:
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE earthquakes(id TEXT PRIMARY KEY, time_kst TEXT, lat REAL, lon REAL, depth_km REAL, mag REAL, mag_type TEXT, place TEXT);
    CREATE TABLE power_hourly(ts TEXT PRIMARY KEY, date TEXT, hour INTEGER, actual_mw INTEGER, pred_ensemble_mw INTEGER, pred_linear_mw INTEGER,
                              pred_gbm_mw INTEGER, pred_naive_mw INTEGER, temp_c REAL, is_holiday INTEGER);
    CREATE TABLE fire_detections(sat TEXT, date_kst TEXT, lat REAL, lon REAL, frp REAL, is_static INTEGER, cell TEXT, near TEXT);
    CREATE TABLE fire_weather(cell TEXT, near TEXT, date TEXT, tmax_c REAL, rhmin REAL, wind_kmh REAL, precip_mm REAL, ffwi REAL, kind TEXT, PRIMARY KEY(cell, date));
    CREATE TABLE _catalog(table_name TEXT, column_name TEXT, description TEXT);
    """)
    with (REPO / "geo-data-pipeline" / "data" / "events.csv").open(encoding="utf-8", newline="") as f:
        con.executemany("INSERT INTO earthquakes VALUES (?,?,?,?,?,?,?,?)",
                        [(r["id"], r["time_kst"], float(r["lat"]), float(r["lon"]), float(r["depth_km"] or 0), float(r["mag"]), r["mag_type"], r["place"])
                         for r in csv.DictReader(f) if r.get("type", "earthquake") == "earthquake" and r["mag"]])
    p = json.loads((REPO / "power-demand" / "explorer" / "predictions.json").read_text(encoding="utf-8"))
    t0, hol, m = datetime.fromisoformat(p["start"]), set(p["holiday"]), p["models"]
    con.executemany("INSERT INTO power_hourly VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [((t := t0 + timedelta(hours=i)).strftime("%Y-%m-%d %H:00"), t.strftime("%Y-%m-%d"), t.hour, p["actual"][i], m["ens"][i], m["linear"][i],
                      m["gbm"][i], m["naive"][i], p["temp"][i], int(t.strftime("%Y-%m-%d") in hol)) for i in range(p["n"])])
    d_rows, w_rows = _fire_rows()
    con.executemany("INSERT INTO fire_detections VALUES (?,?,?,?,?,?,?,?)", d_rows)
    con.executemany("INSERT INTO fire_weather VALUES (?,?,?,?,?,?,?,?,?)", w_rows)
    for tname, (desc, cols) in CATALOG.items():
        con.execute("INSERT INTO _catalog VALUES (?,?,?)", (tname, "", desc))
        con.executemany("INSERT INTO _catalog VALUES (?,?,?)", [(tname, c, d) for c, d in cols.items()])
    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in CATALOG}
    con.close()
    return counts


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
