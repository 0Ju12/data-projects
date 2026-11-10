"""전체 실험: python -m sensoranom.run  →  reports/results.json · reports/*.png · reports/REPORT.md

1) 부품별 이상 탐지: 정상 사이클(시간 순 앞 70%)로 학습 → 나머지 사이클에서 ROC-AUC, 1% 오경보 임계값의 상태·심각도별 탐지율
2) 스트리밍 경보: 사이클을 원래 순서대로 흘려보내며 k=1·3 연속 규칙의 경보 지연과 정상 구간 오경보
3) 지도학습 진단: 무작위 분할 vs 연속 구간 분할 정확도 비교 (이웃 사이클이 거의 같아 무작위 분할은 성능을 부풀림)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import train_test_split

from . import data, detect

ROOT = Path(__file__).resolve().parent.parent
COLS = {"cooler": 0, "valve": 1, "pump": 2, "accumulator": 3}


def _train_idx(mask, Y):
    """mask 인 사이클을 시간 순으로 세워 앞 60% (안정 플래그 0 인 사이클이 30개 이상이면 그것만)"""
    cand = np.where(mask & (Y[:, 4] == 0))[0]
    if len(cand) < 30:
        cand = np.where(mask)[0]
    return cand[: int(len(cand) * 0.6)]


def evaluate(X, Y, comp, regime_aware: bool):
    """점수는 '임계값 대비 비율'(1 초과 = 이상)로 통일해 운전 구간이 달라도 같은 기준으로 비교"""
    n, c = len(X), COLS[comp]
    normal = Y[:, c] == data.NORMAL[comp]
    ratio = np.zeros(n)
    tr_all = []
    regimes = sorted(set(Y[:, 0])) if regime_aware else [None]
    for r in regimes:
        in_r = np.ones(n, bool) if r is None else (Y[:, 0] == r)
        tr = _train_idx(normal & in_r, Y)
        det = detect.fit_detector(X[tr])
        ratio[in_r] = det.score(X[in_r]) / det.threshold
        tr_all.append(tr)
    tr_idx = np.concatenate(tr_all)
    test = ~np.isin(np.arange(n), tr_idx)
    y = (~normal[test]).astype(int)
    flags = ratio[test] > 1
    per_level = {str(int(lv)): {"n": int((Y[test, c] == lv).sum()), "flagged": round(float(flags[Y[test, c] == lv].mean()), 3)} for lv in sorted(set(Y[test, c]))}
    stream = {}
    for k in (1, 3):
        al = detect.debounce(ratio > 1, k)
        lat = detect.alert_latency(~normal, al)
        held_normal = normal & test
        ok = [x for x in lat if x >= 0]
        stream[f"k={k}"] = {"fault_segments": len(lat), "detected": len(ok), "median_latency_cycles": float(np.median(ok)) if ok else None,
                            "false_alarms_per_100_normal": round(float(al[held_normal].mean() * 100), 2)}
    res = {"train_cycles": int(len(tr_idx)), "test_cycles": int(test.sum()), "roc_auc": round(float(roc_auc_score(y, ratio[test])), 4),
           "test_normal_false_alarm": round(float(flags[y == 0].mean()), 4), "test_fault_detected": round(float(flags[y == 1].mean()), 4),
           "by_level": per_level, "stream": stream}
    return res, ratio


def anomaly(X, Y):
    out, streams = {}, {}
    for comp in COLS:
        g, rg = evaluate(X, Y, comp, False)
        out[comp] = {"global": g}
        best = rg
        if comp != "cooler":                 # 냉각기 상태 = 운전 구간. 냉각기 자체는 전역 모델만
            r, rr = evaluate(X, Y, comp, True)
            out[comp]["regime_aware"] = r
            best = rr
        streams[comp] = (best, 1.0, Y[:, COLS[comp]])
    return out, streams


def diagnosis(X, Y, seed=0):
    """부품 상태 분류. 모델 2종(RandomForest, 표준화+LDA) × 분할 2종(무작위 70/30, 시간 연속 구간 70/30)"""
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    models = {"random_forest": lambda: RandomForestClassifier(n_estimators=300, random_state=seed, n_jobs=-1),
              "lda": lambda: make_pipeline(StandardScaler(), LinearDiscriminantAnalysis())}
    out = {}
    tr_b, te_b = detect.block_split(len(X))
    for comp, c in COLS.items():
        y = Y[:, c].astype(int)
        tr_r, te_r = train_test_split(np.arange(len(X)), test_size=0.3, random_state=seed, stratify=y)
        res = {}
        for mname, mk in models.items():
            for split, (tr, te) in {"random_split": (tr_r, te_r), "block_split": (tr_b, te_b)}.items():
                clf = mk().fit(X[tr], y[tr])
                p = clf.predict(X[te])
                res[f"{mname}/{split}"] = {"accuracy": round(float((p == y[te]).mean()), 4), "macro_f1": round(float(f1_score(y[te], p, average="macro")), 4)}
                if mname == "random_forest" and split == "block_split":
                    imp = sorted(zip(data.feature_names(), clf.feature_importances_), key=lambda x: -x[1])[:5]
                    res["rf_top_features"] = [[k, round(float(v), 4)] for k, v in imp]
        out[comp] = res
    return out


def plots(streams, outdir: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(4, 1, figsize=(10, 9), sharex=True)
    for ax, (comp, (s, thr, lv)) in zip(axes, streams.items()):
        normal = lv == data.NORMAL[comp]
        ax.scatter(np.where(normal)[0], s[normal], s=3, c="#2563eb", label="normal")
        ax.scatter(np.where(~normal)[0], s[~normal], s=3, c="#dc2626", label="degraded")
        ax.axhline(thr, color="#111", lw=1, ls="--")
        ax.set_yscale("log")
        ax.set_ylabel(comp)
    axes[0].legend(loc="upper right", markerscale=4, fontsize=8)
    axes[-1].set_xlabel("cycle (time order)")
    fig.suptitle("Anomaly score / threshold per component (regime-aware except cooler; dashed = 1)")
    fig.tight_layout()
    fig.savefig(outdir / "scores.png", dpi=120)
    plt.close(fig)


def main():
    plt_ok = True
    X, Y = data.load(ROOT / "raw", ROOT / "cache")
    res = {"dataset": {"cycles": int(len(X)), "features": int(X.shape[1])}}
    res["anomaly"], streams = anomaly(X, Y)
    res["diagnosis"] = diagnosis(X, Y)
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        plots(streams, out)
    except ImportError:
        plt_ok = False
    for k, v in res["anomaly"].items():
        for mode, m in v.items():
            print(k, mode, {"auc": m["roc_auc"], "fa": m["test_normal_false_alarm"], "det": m["test_fault_detected"], "k3": m["stream"]["k=3"]})
    for k, v in res["diagnosis"].items():
        print(k, {m: r["accuracy"] for m, r in v.items() if isinstance(r, dict)})
    return res, plt_ok


if __name__ == "__main__":
    main()
