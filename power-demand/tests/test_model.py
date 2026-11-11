from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from powerfc import data, model

ROOT = Path(__file__).resolve().parent.parent


def test_load_demand_shape_and_hour_mapping():
    s = data.load_demand(ROOT / "data" / "kpx_hourly_demand_2025.csv")
    assert len(s) == 365 * 24
    d = dict(s)
    assert datetime(2025, 1, 1, 0) in d and datetime(2025, 12, 31, 23) in d     # '1시' 열 = 0시 시작
    assert d[datetime(2025, 1, 1, 0)] == 62256


def test_day_type_holidays_and_weekend():
    assert model.day_type(date(2025, 10, 6)) == 2      # 추석(월)
    assert model.day_type(date(2025, 11, 8)) == 1      # 토
    assert model.day_type(date(2025, 11, 9)) == 2      # 일
    assert model.day_type(date(2025, 11, 10)) == 0     # 평일


def test_features_use_only_lags_of_24h_or_more():
    base = datetime(2025, 3, 1)
    series = {base + timedelta(hours=h): 1000.0 + h for h in range(24 * 15)}
    ts, X, y = model.build_features(series, None, use_temp=False)
    t = ts[0]
    i = 0
    assert X[i, -4] == series[t - timedelta(hours=24)] and X[i, -3] == series[t - timedelta(hours=168)]
    # 타깃 값 자체가 특징에 들어가지 않음 (같은 시각 값이 어느 열에도 없어야 함)
    assert not np.any(np.isclose(X[:, -4:-1], y[:, None]))


def test_metrics():
    y, p = np.array([100.0, 200.0]), np.array([110.0, 180.0])
    assert np.isclose(model.mape(y, p), 10.0)
    ts = [datetime(2025, 1, 1, 1), datetime(2025, 1, 1, 2)]
    assert np.isclose(model.daily_peak_error(ts, y, p), 10.0)    # 최대 200 vs 180


def test_explorer_predictions_match_report():
    """탐색기 데이터가 시험 구간 전체(92일 × 24시간)이고, 앙상블 MAPE 가 results.json 과 같은지"""
    import json
    p = json.loads((ROOT / "explorer" / "predictions.json").read_text(encoding="utf-8"))
    rep = json.loads((ROOT / "reports" / "results.json").read_text(encoding="utf-8"))
    assert p["n"] == 92 * 24 and len(p["actual"]) == p["n"]
    assert set(p["models"]) == {"naive", "linear", "gbm", "ens"}
    a = np.array(p["actual"], float)
    ens = np.array(p["models"]["ens"], float)
    assert abs(model.mape(a, ens) - rep["results"]["ensemble(linear, gbm+temp)"]["mape"]) < 0.02
