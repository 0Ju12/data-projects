import json
import math
import random
import urllib.error
from datetime import datetime
from pathlib import Path

import pytest

from geopipe import analyze, cli, fetch, store, transform

FIX = Path(__file__).parent / "fixtures" / "usgs_sample.geojson"
CFG = json.loads((Path(__file__).parent.parent / "config.json").read_text(encoding="utf-8"))


def features():
    return json.loads(FIX.read_text(encoding="utf-8"))["features"]


def test_to_event_converts_time_to_kst():
    e = transform.to_event(features()[0])
    t_utc = datetime.strptime(e.time_utc, "%Y-%m-%dT%H:%M:%SZ")
    t_kst = datetime.strptime(e.time_kst, "%Y-%m-%d %H:%M:%S")
    assert (t_kst - t_utc).total_seconds() == 9 * 3600


def test_clean_dedupes_and_keeps_latest_revision():
    fs = features()
    newer = json.loads(json.dumps(fs[0]))
    newer["properties"]["updated"] += 1000
    newer["properties"]["mag"] = 9.9
    events, q = transform.clean(fs + [newer])
    assert events[fs[0]["id"]].mag == 9.9
    assert q.duplicates == 1 and q.revised == 1
    assert q.kept == len({f["id"] for f in fs})


def test_clean_quarantines_bad_records():
    fs = features()
    bad_mag = json.loads(json.dumps(fs[0])); bad_mag["id"] = "x1"; bad_mag["properties"]["mag"] = None
    bad_depth = json.loads(json.dumps(fs[0])); bad_depth["id"] = "x2"; bad_depth["geometry"]["coordinates"][2] = 9999
    blast = json.loads(json.dumps(fs[0])); blast["id"] = "x3"; blast["properties"]["type"] = "quarry blast"
    events, q = transform.clean([bad_mag, bad_depth, blast])
    assert events == {}
    assert (q.no_magnitude, q.out_of_range, q.not_earthquake) == (1, 1, 1)


def test_older_revision_does_not_overwrite():
    fs = features()
    events, _ = transform.clean(fs)
    older = json.loads(json.dumps(fs[0])); older["properties"]["updated"] -= 1000; older["properties"]["mag"] = 1.0
    events2, q = transform.clean([older], events)
    assert events2[fs[0]["id"]].mag == events[fs[0]["id"]].mag and q.revised == 0


def test_csv_roundtrip(tmp_path):
    events, _ = transform.clean(features())
    store.save_csv(tmp_path / "e.csv", events)
    back = store.load_csv(tmp_path / "e.csv")
    assert back.keys() == events.keys()
    k = next(iter(events))
    assert back[k] == events[k]


def test_b_value_recovers_synthetic_gr():
    # b=1 인 구텐베르크-리히터 분포에서 뽑은 규모 (Mc=4.0, 0.1 단위로 반올림) → 추정 b 가 1 근처
    random.seed(0)
    beta = math.log(10) * 1.0
    mags = [round(3.95 + random.expovariate(beta), 1) for _ in range(5000)]
    gr = analyze.b_value(mags, mc=4.0)
    assert abs(gr["b"] - 1.0) < 0.06
    assert gr["sigma"] < 0.05


def test_b_value_refuses_small_sample():
    assert analyze.b_value([4.0, 4.1, 4.5])["b"] is None


def test_fetch_splits_when_too_many(monkeypatch):
    calls = []

    def fake_count(region, a, b, opener=None):
        days = (b - a).days
        return 30000 if days > 100 else 10

    def fake_get(url, retries=4, opener=None):
        calls.append(url)
        return {"features": [{"id": url[-10:]}]}
    monkeypatch.setattr(fetch, "count", fake_count)
    monkeypatch.setattr(fetch, "_get", fake_get)
    out = fetch.fetch(CFG["regions"][0], datetime(2024, 1, 1), datetime(2024, 12, 31))
    assert len(out) >= 4 and len(calls) == len(out)


def test_get_retries_then_raises(monkeypatch):
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    n = {"c": 0}

    def opener(req, timeout=60):
        n["c"] += 1
        raise urllib.error.URLError("down")
    with pytest.raises(urllib.error.URLError):
        fetch._get("https://example.invalid", retries=2, opener=opener)
    assert n["c"] == 3


def test_offline_run_builds_outputs(tmp_path):
    out = cli.run(CFG, tmp_path / "data", tmp_path / "docs", offline=FIX, now=datetime(2026, 10, 9))
    assert out["kept"] > 0
    html = (tmp_path / "docs" / "index.html").read_text(encoding="utf-8")
    assert "leaflet" in html and "데이터 품질" in html
    s = json.loads((tmp_path / "data" / "summary.json").read_text(encoding="utf-8"))
    assert s["regions"][0]["n"] == out["kept"]
    assert (tmp_path / "data" / "events.sqlite").exists()


def test_monthly_counts_fills_gaps():
    from geopipe.transform import Event
    mk = lambda t: Event("i" + t, t, t, 0, 37, 129, 10, 3.0, "mb", "", "", "earthquake")
    out = analyze.monthly_counts([mk("2024-01-05T00:00:00Z"), mk("2024-04-01T00:00:00Z"), mk("2024-04-02T00:00:00Z")])
    assert out == [("2024-01", 1), ("2024-02", 0), ("2024-03", 0), ("2024-04", 2)]
