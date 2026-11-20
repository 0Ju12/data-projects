"""수집 거르기·분석 쿼리를 작은 가짜 원본으로 확인 (네트워크 없이)."""
import csv
import json
from pathlib import Path

import pytest

from etl import analyze, fetch
from etl.sources import EMBER_COLS, OWID_COLS

EMBER_HEADER = list(EMBER_COLS) + ["Area type", "Continent"]


def _ember_rows():
    rows = []
    # 한국 2022~2025 매달: 석탄 40, 가스 30, 원자력 20, 태양광(봄에 큼) + 나머지 기타
    for y in range(2022, 2026):
        for m in range(1, 13):
            solar = 8.0 if m in (4, 5) else 4.0
            shares = {"Coal": 40.0, "Gas": 30.0, "Nuclear": 20.0, "Solar": solar, "Wind": 1.0, "Hydro": 9.0 - solar}
            for src, sh in shares.items():
                rows.append(["South Korea", f"{y}-{m:02d}-01", src, sh / 2, sh, "", "Country or economy", "Asia"])
            rows.append(["South Korea", f"{y}-{m:02d}-01", "Total generation", 50, 100, 400 - m, "Country or economy", "Asia"])
            rows.append(["South Korea", f"{y}-{m:02d}-01", "Fossil", 35, 70, "", "Country or economy", "Asia"])   # 묶음 행 — 버려야 함
    rows.append(["Narnia", "2025-01-01", "Coal", 1, 100, "", "Country or economy", "Europe"])                   # 대상 아닌 나라
    rows.append(["South Korea", "2010-01-01", "Coal", 1, 50, "", "Country or economy", "Asia"])                # 시작 달 이전
    return rows


def _owid_rows():
    out = []
    for c in ("South Korea", "United Kingdom"):
        for y in range(2000, 2026):
            coal = 46 - (y - 2000) * 0.5 if c == "South Korea" else max(0.0, 30 - (y - 2005) * 3)
            solar = max(0.0, (y - 2016) * 0.8) if c == "South Korea" else max(0.0, (y - 2012) * 0.6)
            row = {k: "" for k in OWID_COLS}
            row.update(country=c, year=y, population=1, electricity_generation=300 + y - 2000, per_capita_electricity=10000,
                       carbon_intensity_elec=500 - (y - 2000) * 3, coal_share_elec=coal, gas_share_elec=100 - coal - 1 - 30 - 1 - 0.5 - solar - 0.5, oil_share_elec=1,
                       nuclear_share_elec=30, hydro_share_elec=1, wind_share_elec=0.5, solar_share_elec=solar, biofuel_share_elec=0.5,
                       other_renewables_share_elec_exc_biofuel=0, low_carbon_share_elec=32 + solar, renewables_share_elec=2 + solar,
                       fossil_share_elec=68 - solar)
            out.append([row[k] for k in OWID_COLS])
    return out


@pytest.fixture
def raw(tmp_path):
    e, o = tmp_path / "ember.csv", tmp_path / "owid.csv"
    with e.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(EMBER_HEADER); w.writerows(_ember_rows())
    with o.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(OWID_COLS); w.writerows(_owid_rows())
    return tmp_path, e, o


def test_fetch_keeps_only_target_countries_sources_and_months(raw):
    d, e, o = raw
    rep = fetch.fetch_all(str(e), str(o), d / "data")
    assert rep["ember"]["status"] == "ok" and rep["owid"]["status"] == "ok"
    rows = list(csv.DictReader((d / "data" / "ember_monthly.csv").open(encoding="utf-8")))
    assert {r["area"] for r in rows} == {"South Korea"}
    assert "Fossil" not in {r["source"] for r in rows}            # 묶음 행은 겹쳐 세지 않게 버림
    assert min(r["month"] for r in rows) >= "2015-01-01"
    assert rep["ember"]["rows"] == 4 * 12 * 7


def test_schema_change_keeps_previous_file(raw):
    d, e, o = raw
    fetch.fetch_all(str(e), str(o), d / "data")
    before = (d / "data" / "ember_monthly.csv").read_bytes()
    bad = d / "bad.csv"
    bad.write_text("Area,Date\nSouth Korea,2025-01-01\n", encoding="utf-8")
    rep = fetch.fetch_all(str(bad), str(o), d / "data")
    assert rep["ember"]["status"] == "kept_previous" and "열이 바뀌었" in rep["ember"]["error"]
    assert (d / "data" / "ember_monthly.csv").read_bytes() == before


def test_fetch_is_deterministic(raw):
    d, e, o = raw
    fetch.fetch_all(str(e), str(o), d / "a")
    fetch.fetch_all(str(e), str(o), d / "b")
    assert (d / "a" / "ember_monthly.csv").read_bytes() == (d / "b" / "ember_monthly.csv").read_bytes()


def test_queries_answer_the_questions(raw):
    d, e, o = raw
    fetch.fetch_all(str(e), str(o), d / "data")
    r = analyze.run_queries(d / "data")
    mix = r["mix_yearly"]
    assert all(abs(m["coal"] + m["nuclear"] + m["gas"] + m["other"] + m["wind"] + m["solar"] - 100) < 1e-6 for m in mix)
    kr = next(c for c in r["coal_change"] if c["country"] == "한국")
    assert kr["coal_2015"] == pytest.approx(38.5) and kr["coal_last"] == pytest.approx(33.5) and kr["coal_peak_year"] == 2000
    uk = next(s for s in r["solar_growth"] if s["country"] == "영국")
    assert (uk["first_1pct"], uk["first_5pct"], uk["first_10pct"]) == (2014, 2021, None)   # 0.6%p 씩: 2014년 1.2%, 2021년 5.4%
    # 계절성: 4·5월 태양광 8%, 나머지 4%
    assert {s["solar_share"] for s in r["solar_seasonal"] if s["mon"] in (4, 5)} == {8.0}
    # 달별 구성: 다 찬 최근 4개 연도, 묶음별 합이 100
    mm = r["mix_monthly"]
    assert (mm[0]["from_year"], mm[0]["to_year"]) == (2022, 2025)
    for mon in range(1, 13):
        assert sum(x["share"] for x in mm if x["mon"] == mon) == pytest.approx(100)
    # 12개월 이동 평균은 12달이 찬 뒤부터만 의미 — 창 크기 열로 구분
    im = [x for x in r["intensity_monthly"] if x["area"] == "한국"]
    assert im[0]["months_in_window"] == 1 and im[11]["months_in_window"] == 12
    assert r["meta"]["owid_last_year"] == 2025


def test_build_embeds_data_without_closing_script(raw, tmp_path):
    d, e, o = raw
    fetch.fetch_all(str(e), str(o), d / "data")
    out = analyze.build(tmp_path / "index.html", d / "data")
    html = out.read_text(encoding="utf-8")
    assert "__DATA__" not in html and "const D={" in html
    blob = html.split("const D=", 1)[1].split(";\nconst G=", 1)[0]
    assert json.loads(blob.replace("<\\/", "</"))["meta"]["groups"][0] == "석탄"
