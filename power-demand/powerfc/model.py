"""하루 전(day-ahead) 시간별 전력 수요 예측.

예측 시점: D-1 일 자정 무렵, D 일 24시간을 한꺼번에 예측. 그래서 수요 값은 '24시간 이상 지난 값'만 쓸 수 있습니다
(어제 같은 시각, 지난주 같은 시각, 어제 하루 평균). 기온은 실제 관측값을 '완벽한 기온 예보'로 가정해 넣습니다 — 실제 운영에서는
예보 오차만큼 성능이 떨어지므로, 기온 없이 한 모델도 같이 비교합니다.

모델
- naive_week: 지난주 같은 요일·시각 값 (계절성 기준선)
- linear: 달력(시각×평일/주말·휴일, 월) + 지연값 + 기온(냉방·난방 도일 형태) 선형 회귀
- gbm: 같은 특징의 HistGradientBoosting
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from .data import is_holiday


def day_type(d) -> int:
    """0 평일, 1 토요일, 2 일요일·공휴일"""
    if is_holiday(d):
        return 2
    wd = d.weekday()
    return 2 if wd == 6 else 1 if wd == 5 else 0


def build_features(series: dict[datetime, float], temp: dict[datetime, float] | None, use_temp: bool = True):
    """(시각 목록, X, y). 지연값이 없는 처음 8일은 버림."""
    times = sorted(series)
    rows, ys, ts = [], [], []
    for t in times:
        l24, l168 = t - timedelta(hours=24), t - timedelta(hours=168)
        if l24 not in series or l168 not in series:
            continue
        prev_day = [series.get(t.replace(hour=0) - timedelta(days=1) + timedelta(hours=h)) for h in range(24)]
        if any(v is None for v in prev_day):
            continue
        dt = day_type(t.date())
        prev_dt = day_type((t - timedelta(days=1)).date())
        f = []
        f += [1.0 if t.hour == h and dt == k else 0.0 for k in range(3) for h in range(24)]     # 시각 × 날 종류
        f += [1.0 if t.month == m else 0.0 for m in range(1, 13)]
        f += [series[l24], series[l168], float(np.mean(prev_day)), 1.0 if prev_dt != dt else 0.0]
        if use_temp:
            tc = temp.get(t) if temp else None
            if tc is None:
                continue
            f += [tc, max(0.0, tc - 24.0), max(0.0, 15.0 - tc), max(0.0, tc - 24.0) ** 2, max(0.0, 15.0 - tc) ** 2]
        rows.append(f)
        ys.append(series[t])
        ts.append(t)
    return ts, np.array(rows), np.array(ys)


def mape(y, p) -> float:
    return float(np.mean(np.abs(p - y) / y) * 100)


def daily_peak_error(ts, y, p) -> float:
    """일별 최대수요의 평균 절대 백분율 오차 (전력 계통 운영에서 중요한 지표)"""
    days = {}
    for t, a, b in zip(ts, y, p):
        d = days.setdefault(t.date(), [0, 0])
        d[0], d[1] = max(d[0], a), max(d[1], b)
    return float(np.mean([abs(b - a) / a for a, b in days.values()]) * 100)


def naive_week(series: dict[datetime, float], ts) -> np.ndarray:
    return np.array([series[t - timedelta(hours=168)] for t in ts])
