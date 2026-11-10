"""python -m powerfc.run → reports/results.json, reports/forecast.png

학습: 1~9월, 시험: 10~12월 (추석 연휴 포함). 시험 기간은 한 번도 학습에 쓰지 않습니다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import data, model

ROOT = Path(__file__).resolve().parent.parent
SPLIT = datetime(2025, 10, 1)


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


def main():
    series = dict(data.load_demand(ROOT / "data" / "kpx_hourly_demand_2025.csv"))
    temp = data.load_weather(ROOT / "data" / "weather_2025.csv")
    res, preds = evaluate(series, temp)
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    summary = {"hours": len(series), "train": "2025-01-08 ~ 2025-09-30", "test": "2025-10-01 ~ 2025-12-31",
               "peak_MW": max(series.values()), "peak_time": max(series, key=series.get).isoformat(), "results": res}
    (out / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        plot(preds, out)
    except ImportError:
        pass
    for k, v in res.items():
        print(f"{k:28s} MAPE {v['mape']:5.2f}%  peak {v['peak_mape']:5.2f}%  holiday {v['holiday_mape']:5.2f}%  other {v['non_holiday_mape']:5.2f}%")


if __name__ == "__main__":
    main()
