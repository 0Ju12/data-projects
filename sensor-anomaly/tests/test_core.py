import numpy as np

from sensoranom import data, detect


def test_cycle_features_linear_ramp():
    x = np.vstack([np.linspace(0, 10, 101), np.full(101, 3.0)])
    f = data.cycle_features(x)
    names = data.STATS
    assert np.isclose(f[0, names.index("mean")], 5.0)
    assert np.isclose(f[0, names.index("slope")], 10.0)        # 사이클 길이를 1로 본 기울기
    assert np.isclose(f[1, names.index("std")], 0.0) and np.isclose(f[1, names.index("diff_rms")], 0.0)
    assert f.shape == (2, len(names))


def test_feature_names_match_count():
    assert len(data.feature_names()) == len(data.SENSORS) * len(data.STATS) == 136


def test_block_split_contiguous_and_disjoint():
    tr, te = detect.block_split(100, n_blocks=10, test_blocks=(7, 8, 9))
    assert set(tr) & set(te) == set()
    assert len(tr) + len(te) == 100
    assert te.min() == 70 and te.max() == 99 and np.all(np.diff(te) == 1)


def test_debounce_requires_consecutive():
    f = np.array([1, 0, 1, 1, 0, 1, 1, 1, 1], bool)
    assert detect.debounce(f, 1).tolist() == f.tolist()
    assert detect.debounce(f, 3).tolist() == [0, 0, 0, 0, 0, 0, 0, 1, 1]


def test_alert_latency():
    fault = np.array([0, 0, 1, 1, 1, 0, 0, 1, 1, 0], bool)
    alerts = np.array([0, 0, 0, 1, 1, 0, 0, 0, 0, 0], bool)
    assert detect.alert_latency(fault, alerts) == [1, -1]      # 두 번째 고장 구간은 놓침


def test_detector_false_alarm_close_to_target():
    rng = np.random.default_rng(0)
    normal = rng.normal(size=(4000, 10))
    det = detect.fit_detector(normal, fa_rate=0.01)
    fresh = rng.normal(size=(20000, 10))
    fa = (det.score(fresh) > det.threshold).mean()
    assert 0.003 < fa < 0.03
    shifted = rng.normal(loc=2.0, size=(2000, 10))
    assert (det.score(shifted) > det.threshold).mean() > 0.9


def test_forward_chain_folds_train_strictly_before_test():
    folds = detect.forward_chain_folds(100, n_blocks=10, first_test=5)
    assert len(folds) == 5
    for k, (tr, te) in enumerate(folds, start=5):
        assert tr.max() < te.min()                       # 미래로 학습하지 않음
        assert tr.min() == 0 and te.min() == k * 10 and len(te) == 10


def test_block_bootstrap_ci_contains_mean_and_widens_with_autocorrelation():
    rng = np.random.default_rng(1)
    iid = (rng.random(600) < 0.7).astype(float)
    lo, hi = detect.block_bootstrap_ci(iid, block=1)
    assert lo < iid.mean() < hi and hi - lo < 0.1
    runs = np.repeat(rng.random(30) < 0.7, 20).astype(float)  # 20사이클씩 같은 값: 강한 자기상관
    lo1, hi1 = detect.block_bootstrap_ci(runs, block=1)
    lo20, hi20 = detect.block_bootstrap_ci(runs, block=20)
    assert (hi20 - lo20) > 1.5 * (hi1 - lo1)
