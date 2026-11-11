import csv
from pathlib import Path

from firewatch import evaluate, firms, grid, sources, weather

FIRMS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
36.00100,129.39200,330.1,0.4,0.4,2026-11-03,1700,N20,nominal,2.0NRT,290.1,5.1,N
36.00300,129.39100,330.1,0.4,0.4,2026-11-04,1700,N20,nominal,2.0NRT,290.1,5.1,N
36.00200,129.39300,330.1,0.4,0.4,2026-11-05,0400,N20,nominal,2.0NRT,290.1,5.1,D
36.60000,128.70000,340.0,0.4,0.4,2026-11-05,0400,N20,nominal,2.0NRT,290.1,9.0,D
36.61000,128.70000,340.0,0.4,0.4,2026-11-05,0400,N20,low,2.0NRT,290.1,9.0,D
44.80000,37.60000,300.0,0.4,0.4,2026-11-05,0400,N20,nominal,2.0NRT,290.1,1.0,D
"""


def test_land_cells_and_points():
    assert grid.on_land(37.57, 126.98) and grid.on_land(33.40, 126.55)        # 서울, 제주
    assert not grid.on_land(36.0, 131.0) and not grid.on_land(34.0, 125.0)    # 동해, 서해
    cells = grid.land_cells()
    assert 120 < len(cells) < 200 and len(set(cells)) == len(cells)
    assert grid.cell_id(36.60, 128.70) == "36.50_128.50"
    assert grid.cell_center("36.50_128.50") == (36.625, 128.625)
    assert grid.near_city(36.0, 129.39) == "포항 부근"


def test_parse_keeps_korea_and_drops_low_confidence():
    rows = firms.parse(FIRMS_CSV, "N20")
    assert len(rows) == 4                                   # 한국 밖 1건, low 1건 제외
    assert rows[0]["time"] == "1700" and rows[0]["sat"] == "N20"


def test_merge_is_idempotent(tmp_path: Path):
    p = tmp_path / "d.csv"
    rows = firms.parse(FIRMS_CSV, "N20")
    assert firms.merge(p, rows) == 4
    first = p.read_text(encoding="utf-8")
    assert firms.merge(p, rows) == 0                        # 같은 자료를 다시 넣어도 늘지 않음
    assert p.read_text(encoding="utf-8") == first
    assert firms.merge(p, firms.parse(FIRMS_CSV, "N21")) == 4   # 다른 위성은 별개 탐지


def test_static_source_needs_three_distinct_days(tmp_path: Path):
    rows = firms.parse(FIRMS_CSV, "N20")
    known = sources.update(tmp_path / "s.csv", rows)
    assert list(known) == [(36.0, 129.39)] and known[(36.0, 129.39)] == 3
    flags = [sources.is_static(r, known) for r in rows]
    assert flags == [True, True, True, False]               # 안동 쪽 한 번짜리는 화재 의심으로 남음
    # 한 번 판정한 자리는 그날 탐지가 없어도 목록에 남음
    again = sources.update(tmp_path / "s.csv", rows[3:])
    assert (36.0, 129.39) in again
    with (tmp_path / "s.csv").open(encoding="utf-8") as f:
        assert next(csv.DictReader(f))["near"] == "포항 부근"


def test_ffwi_value_and_direction():
    # 손으로 계산한 값: 30℃(86℉), 습도 20%, 풍속 20 mph → 평형 함수율 4.159%, 지수 약 50.0
    assert abs(weather.emc(20, 86) - 4.15855) < 1e-4
    assert abs(weather.ffwi(30, 20, 20 * 1.609344) - 50.05) < 0.1
    assert weather.ffwi(30, 20, 20) > weather.ffwi(30, 60, 20) > weather.ffwi(30, 95, 20)   # 건조할수록 높음
    assert weather.ffwi(20, 30, 40) > weather.ffwi(20, 30, 10)                              # 바람이 셀수록 높음
    assert weather.ffwi(10, 100, 0) >= 0


def test_weather_parse_marks_forecast_and_merge_keeps_observed(tmp_path: Path):
    api = [{"daily": {"time": ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12"], "temperature_2m_max": [12, None, 14, 15],
                      "relative_humidity_2m_min": [55, 33, 65, 60], "wind_speed_10m_max": [9.9, 10.5, 10.3, 12.0], "precipitation_sum": [0, None, 1.5, 0]}}]
    rows = weather.parse(api, ["36.50_128.50"], forecast_days=2)        # 오늘(11-11) + 내일(11-12)
    assert [(r["date"][-2:], r["kind"]) for r in rows] == [("09", "obs"), ("11", "obs"), ("12", "forecast")]   # 값이 빈 날은 건너뜀, 오늘은 obs
    assert rows[1]["precip_mm"] == 1.5 and weather.parse(api, ["x"], 2)[0]["precip_mm"] == 0
    p = tmp_path / "w.csv"
    weather.merge(p, rows)
    obs = dict(rows[1], ffwi=99.0)
    weather.merge(p, [obs, dict(rows[0], kind="forecast", ffwi=1.0)])   # 관측을 예보로 되돌리지 않음
    got = {r["date"]: r for r in weather.load(p)}
    assert got["2026-11-11"]["ffwi"] == 99.0 and got["2026-11-09"]["kind"] == "obs" and got["2026-11-09"]["ffwi"] == rows[0]["ffwi"]
    assert len(got) == 3


def test_kst_date_and_auc():
    assert evaluate.kst_date({"date": "2026-11-03", "time": "1700"}) == "2026-11-04"   # UTC 17시 = 한국 다음 날 02시
    assert evaluate.kst_date({"date": "2026-11-05", "time": "400"}) == "2026-11-05"
    assert evaluate.auc([3, 4], [1, 2]) == 1.0 and evaluate.auc([1, 2], [3, 4]) == 0.0
    assert evaluate.auc([2], [2]) == 0.5 and evaluate.auc([], [1]) is None


def test_evaluate_counts_and_top20():
    cells = grid.land_cells()[:10]
    wx = [{"cell": c, "date": "2026-11-05", "ffwi": float(i), "kind": "obs"} for i, c in enumerate(cells)]
    wx += [{"cell": cells[0], "date": "2026-11-06", "ffwi": 50.0, "kind": "forecast"}]      # 예보는 평가에서 제외
    la, lo = grid.cell_center(cells[9])
    lb, lp = grid.cell_center(cells[2])
    det = [{"lat": la, "lon": lo, "date": "2026-11-05", "time": "0400"}, {"lat": lb, "lon": lp, "date": "2026-11-05", "time": "0400"}]
    ev = evaluate.evaluate(wx, det, "2026-11-05", "2026-11-06")
    assert ev["days"] == 1 and ev["cell_days"] == 10 and ev["positive_cell_days"] == 2
    assert ev["top20_hit"] == 0.5                           # 상위 20%(2칸)에 든 것은 한 칸
    assert 0.5 < ev["auc"] < 1.0
