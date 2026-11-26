"""python -m powerfc.run → reports/results.json, reports/forecast.png

학습: 1~9월, 시험: 10~12월 (추석 연휴 포함). 시험 기간은 한 번도 학습에 쓰지 않습니다.

모델 선택은 시험 구간을 보지 않고 1~9월 안에서만 합니다. 4~9월 각 달을 검증 구간으로 두고 그 이전 데이터로만
학습하는 롤링 원점(expanding window) 교차검증 6겹의 평균 MAPE 로 후보(단일 모델 4개 + 두 모델 평균 6개)를 고른 뒤,
고른 모델만 1~9월 전체로 다시 학습해 시험 구간에서 한 번 평가합니다. 기온은 실측값(완벽한 예보 가정)이라,
기온을 쓰지 않는 후보 중 최선(운영 가능 수치)도 따로 고릅니다.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import data, model

ROOT = Path(__file__).resolve().parent.parent
SPLIT = datetime(2025, 10, 1)
CV_MONTHS = range(4, 10)          # 검증 구간: 4~9월 각 달 (그 달 이전 데이터로만 학습)
MODELS = {"linear": lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
          "gbm": lambda: HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, random_state=0)}


def candidate_predictions(series, temp, lo: datetime, hi: datetime):
    """lo 이전으로 학습해 [lo, hi) 를 예측. 단일 모델 4개 + 두 모델 평균 6개 → {이름: (시각, 실제, 예측)}"""
    out = {}
    for use_temp in (False, True):
        ts, X, y = model.build_features(series, temp, use_temp)
        tr = np.array([t < lo for t in ts])
        te = np.array([lo <= t < hi for t in ts])
        tte = [t for t, m in zip(ts, te) if m]
        for name, mk in MODELS.items():
            out[f"{name}{'+temp' if use_temp else ''}"] = (tte, y[te], mk().fit(X[tr], y[tr]).predict(X[te]))
    for a, b in combinations(list(out), 2):
        if out[a][0] == out[b][0]:
            out[f"avg({a}, {b})"] = (out[a][0], out[a][1], (out[a][2] + out[b][2]) / 2)
    return out


def select(series, temp):
    """롤링 원점 교차검증. 시험 구간(10~12월)은 쓰지 않음."""
    folds = {}
    for m in CV_MONTHS:
        for key, (_, y, p) in candidate_predictions(series, temp, datetime(2025, m, 1), datetime(2025, m + 1, 1)).items():
            folds.setdefault(key, []).append(model.mape(y, p))
    cv = {k: {"mean": round(float(np.mean(v)), 2), "std": round(float(np.std(v)), 2), "folds": [round(x, 2) for x in v]}
          for k, v in folds.items()}
    best = min(cv, key=lambda k: cv[k]["mean"])
    best_no_temp = min((k for k in cv if "temp" not in k), key=lambda k: cv[k]["mean"])
    return cv, best, best_no_temp


def evaluate(series, temp):
    res, preds = {}, {}
    for use_temp in (False, True):
        ts, X, y = model.build_features(series, temp, use_temp)
        tr = np.array([t < SPLIT for t in ts])
        te = ~tr
        tte = [t for t, m in zip(ts, te) if m]
        for name, mk in {"linear": lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
                         "gbm": lambda: HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, random_state=0)}.items():
            m = mk().fit(X[tr], y[tr])
            p = m.predict(X[te])
            key = f"{name}{'+temp' if use_temp else ''}"
            hol = np.array([data.is_holiday(t.date()) for t in tte])
            res[key] = {"mape": round(model.mape(y[te], p), 2), "peak_mape": round(model.daily_peak_error(tte, y[te], p), 2),
                        "holiday_mape": round(model.mape(y[te][hol], p[hol]), 2), "non_holiday_mape": round(model.mape(y[te][~hol], p[~hol]), 2)}
            preds[key] = (tte, y[te], p)
        if not use_temp:
            nv = model.naive_week(series, tte)
            hol = np.array([data.is_holiday(t.date()) for t in tte])
            res["naive_week"] = {"mape": round(model.mape(y[te], nv), 2), "peak_mape": round(model.daily_peak_error(tte, y[te], nv), 2),
                                 "holiday_mape": round(model.mape(y[te][hol], nv[hol]), 2), "non_holiday_mape": round(model.mape(y[te][~hol], nv[~hol]), 2)}
            preds["naive_week"] = (tte, y[te], nv)
    # 앙상블: 휴일에 강한 선형(기온 없음)과 평일에 강한 GBM(+기온)의 단순 평균
    ts, y, a = preds["linear"]
    _, _, b = preds["gbm+temp"]
    if len(a) == len(b):
        p = (a + b) / 2
        hol = np.array([data.is_holiday(t.date()) for t in ts])
        res["ensemble(linear, gbm+temp)"] = {"mape": round(model.mape(y, p), 2), "peak_mape": round(model.daily_peak_error(ts, y, p), 2),
                                             "holiday_mape": round(model.mape(y[hol], p[hol]), 2), "non_holiday_mape": round(model.mape(y[~hol], p[~hol]), 2)}
        preds["ensemble(linear, gbm+temp)"] = (ts, y, p)
    return res, preds


def plot(preds, out: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5))
    for ax, (a, b), title in [(axes[0], (datetime(2025, 10, 1), datetime(2025, 10, 15)), "Oct 1-14 (Chuseok holidays Oct 5-9)"),
                              (axes[1], (datetime(2025, 12, 15), datetime(2025, 12, 29)), "Dec 15-28 (winter, Christmas)")]:
        ts, y, _ = preds["gbm+temp"]
        m = [a <= t < b for t in ts]
        tt = [t for t, k in zip(ts, m) if k]
        ax.plot(tt, np.array(y)[m] / 1000, color="#111", lw=1.4, label="actual")
        for key, col in [("naive_week", "#9ca3af"), ("linear", "#2563eb"), ("gbm+temp", "#dc2626"), ("ensemble(linear, gbm+temp)", "#059669")]:
            ax.plot(tt, np.array(preds[key][2])[m] / 1000, color=col, lw=1, label=key)
        ax.set_title(title, fontsize=10)
        ax.set_ylabel("GW")
    axes[0].legend(fontsize=8, ncol=4)
    fig.tight_layout()
    fig.savefig(out / "forecast.png", dpi=120)
    plt.close(fig)


def export(preds, temp, path: Path):
    """탐색기(explorer/index.html)용 시험 구간 시간별 실제·예측값 (MW 정수)"""
    ts, y, _ = preds["ensemble(linear, gbm+temp)"]
    keys = {"naive": "naive_week", "linear": "linear", "gbm": "gbm+temp", "ens": "ensemble(linear, gbm+temp)"}
    out = {"start": ts[0].isoformat(), "n": len(ts), "actual": [int(round(v)) for v in y],
           "temp": [None if temp.get(t) is None else round(float(temp[t]), 1) for t in ts],
           "holiday": sorted({t.date().isoformat() for t in ts if data.is_holiday(t.date())}),
           "models": {k: [int(round(v)) for v in preds[src][2]] for k, src in keys.items()}}
    assert all(len(v) == len(ts) for v in out["models"].values())
    assert all(b - a == timedelta(hours=1) for a, b in zip(ts, ts[1:])), "시험 구간이 1시간 간격으로 이어져야 함"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")


def main():
    series = dict(data.load_demand(ROOT / "data" / "kpx_hourly_demand_2025.csv"))
    temp = data.load_weather(ROOT / "data" / "weather_2025.csv")
    res, preds = evaluate(series, temp)
    cv, best, best_no_temp = select(series, temp)
    final = candidate_predictions(series, temp, SPLIT, datetime(2026, 1, 1))     # 시험 구간 평가는 여기서 한 번

    def scores(key):
        ts, y, p = final[key]
        hol = np.array([data.is_holiday(t.date()) for t in ts])
        return {"mape": round(model.mape(y, p), 2), "peak_mape": round(model.daily_peak_error(ts, y, p), 2),
                "holiday_mape": round(model.mape(y[hol], p[hol]), 2), "non_holiday_mape": round(model.mape(y[~hol], p[~hol]), 2)}
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    summary = {"hours": len(series), "train": "2025-01-08 ~ 2025-09-30", "test": "2025-10-01 ~ 2025-12-31",
               "peak_MW": max(series.values()), "peak_time": max(series, key=series.get).isoformat(), "results": res,
               "selection": {"method": "rolling-origin CV, validation months 2025-04..2025-09, mean MAPE",
                             "selected": best, "selected_test": scores(best),
                             "selected_without_temperature": best_no_temp, "selected_without_temperature_test": scores(best_no_temp),
                             "cv": dict(sorted(cv.items(), key=lambda kv: kv[1]["mean"]))}}
    (out / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        plot(preds, out)
    except ImportError:
        pass
    export(preds, temp, ROOT / "explorer" / "predictions.json")
    for k, v in res.items():
        print(f"{k:28s} MAPE {v['mape']:5.2f}%  peak {v['peak_mape']:5.2f}%  holiday {v['holiday_mape']:5.2f}%  other {v['non_holiday_mape']:5.2f}%")
    print(f"CV 선택: {best} (CV {cv[best]['mean']}%) → 시험 {summary['selection']['selected_test']['mape']}%")
    print(f"기온 없이 CV 선택: {best_no_temp} (CV {cv[best_no_temp]['mean']}%) → 시험 {summary['selection']['selected_without_temperature_test']['mape']}%")


if __name__ == "__main__":
    main()
