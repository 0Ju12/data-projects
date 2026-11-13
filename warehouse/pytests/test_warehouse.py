"""작은 가짜 원본으로 dbt 프로젝트와 실행 도구를 끝까지 돌려 보는 테스트.

실제 자료 파일에 기대지 않도록 원본 경로를 dbt 변수로 바꿔 넣습니다.
"""
import csv
import json
import shutil
from datetime import date, datetime, timedelta

import duckdb
import pytest

from wh import pipeline as P
from wh.sources import jobs as J
from wh.report import build_report, lineage

pytestmark = pytest.mark.skipif(shutil.which(P.os.environ.get("DBT_BIN", "dbt")) is None, reason="dbt 가 설치돼 있지 않음")

QUAKE_HEAD = ["id", "time_utc", "time_kst", "updated", "lat", "lon", "depth_km", "mag", "mag_type", "place", "status", "type"]


def ms(s):
    return int(datetime.fromisoformat(s).timestamp() * 1000)


def write_quakes(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(QUAKE_HEAD)
        w.writerows(rows)


def quake(i, mag, updated, status="automatic", place="10 km E of Ulsan, South Korea"):
    return [i, "2025-03-01T00:00:00Z", "2025-03-01 09:00:00", ms(updated), 35.5, 129.9, 10.0, mag, "mb", place, status, "earthquake"]


def job(source, jid, title, posted, skills="", lo="", hi="", remote="true"):
    return {"source": source, "job_id": jid, "title": title, "company": "Acme", "location": "", "remote": remote,
            "posted_at_utc": posted, "salary_min": lo, "salary_max": hi, "url": "https://example.org/" + jid, "skills": skills}


@pytest.fixture
def src(tmp_path):
    """3일치 수요(1시~24시 열), 72시간 기온, 지진 3건"""
    days = [date(2025, 3, 1) + timedelta(days=i) for i in range(3)]
    with (tmp_path / "demand.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["날짜"] + [f"{h}시" for h in range(1, 25)])
        for k, d in enumerate(days):
            w.writerow([d.isoformat()] + [50000 + 1000 * k + 100 * h for h in range(1, 25)])
    with (tmp_path / "weather.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "서울", "부산", "대전", "광주", "mean"])
        t = datetime(2025, 3, 1)
        for h in range(72):
            w.writerow([(t + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M"), 5, 7, 6, 6, 6.0])
    write_quakes(tmp_path / "quakes.csv", [
        quake("a1", 4.5, "2025-03-01T01:00:00"), quake("a2", 5.0, "2025-03-01T01:00:00", "reviewed"),
        quake("a3", 4.1, "2025-03-01T01:00:00", place="90 km SSE of Tateyama, Japan")])
    J.save({}, tmp_path / "jobs.csv")
    ex = {}
    J.merge(ex, [job("remoteok", "1", "Senior Data Engineer", "2025-03-01T10:00:00Z", "Python|SQL|dbt|Data Engineer (role)", 90000, 130000),
                 job("remoteok", "2", "Registered Nurse", "2025-03-02T10:00:00Z", "", 110, 130),
                 job("arbeitnow", "be-dev-1", "Backend Developer (m/w/d)", "2025-03-03T08:00:00Z", "Python|Backend (role)"),
                 job("arbeitnow", "koch-2", "Teilzeitkraft Küche", "2025-03-10T08:00:00Z", "")], "2025-03-11", "v1")
    J.save(ex, tmp_path / "jobs.csv")
    J.log_fetch([{"run_date": "2025-03-11", "source": "remoteok", "fetched": 2, "new": 2, "changed": 0, "pages": 1, "overlap": "first_run"},
                 {"run_date": "2025-03-11", "source": "arbeitnow", "fetched": 2, "new": 2, "changed": 0, "pages": 1, "overlap": "first_run"}], tmp_path / "fetch.csv")
    return {"vars": {"quakes_csv": str(tmp_path / "quakes.csv"), "demand_csv": str(tmp_path / "demand.csv"),
                     "weather_csv": str(tmp_path / "weather.csv"), "quake_fresh_days": 100000,
                     "jobs_csv": str(tmp_path / "jobs.csv"), "jobs_fetch_csv": str(tmp_path / "fetch.csv")},
            "db": str(tmp_path / "wh.duckdb"), "target": str(tmp_path / "target"), "dir": tmp_path}


def build(src, *args):
    return P.dbt(["build", *args], src["vars"], src["db"], target_path=src["target"])


def q(src, sql):
    con = duckdb.connect(src["db"], read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_build_passes_and_shapes(src):
    p = build(src)
    assert p.returncode == 0, p.stdout[-2000:]
    assert q(src, "select count(*) from fct_demand_hourly")[0][0] == 72
    assert q(src, "select count(*), min(hours), max(hours) from fct_demand_daily")[0] == (3, 24, 24)


def test_hour_24_stays_on_its_own_day(src):
    """'24시' 는 그날 23:00 에 시작하는 구간 — 다음 날 0시로 넘어가면 날짜별 24행이 깨진다"""
    assert build(src).returncode == 0
    start, day, mw = q(src, "select hour_start_kst, demand_date, demand_mw from fct_demand_hourly where demand_date = '2025-03-01' and hour_ending = 24")[0]
    assert start == datetime(2025, 3, 1, 23, 0) and day == date(2025, 3, 1) and mw == 50000 + 2400
    first = q(src, "select hour_start_kst from fct_demand_hourly where demand_date = '2025-03-02' and hour_ending = 1")[0][0]
    assert first == datetime(2025, 3, 2, 0, 0)


def test_daily_summary_values(src):
    assert build(src).returncode == 0
    peak, low, hour, lf = q(src, "select peak_mw, min_mw, peak_hour_ending, load_factor from fct_demand_daily where demand_date = '2025-03-02'")[0]
    assert (peak, low, hour) == (51000 + 2400, 51000 + 100, 24)
    assert lf == pytest.approx((51000 + 1250) / (51000 + 2400), abs=1e-4)


def test_duplicate_quake_id_fails_the_build(src):
    """같은 지진 ID 가 두 번 들어오면 unique 테스트가 막아야 한다"""
    rows = [quake("a1", 4.5, "2025-03-01T01:00:00"), quake("a1", 4.6, "2025-03-01T02:00:00")]
    write_quakes(src["dir"] / "quakes.csv", rows)
    p = build(src)
    assert p.returncode != 0
    assert "unique_stg_quakes_quake_id" in json.dumps(P.run_results(P.Path(src["target"]))["failed"])


def test_out_of_range_magnitude_fails(src):
    write_quakes(src["dir"] / "quakes.csv", [quake("a1", 45.0, "2025-03-01T01:00:00")])
    assert build(src).returncode != 0


def test_missing_hour_is_caught(src):
    """한 시간이 비면(빈 칸) not_null 과 '하루 24행' 검사가 잡는다"""
    lines = (src["dir"] / "demand.csv").read_text(encoding="utf-8").splitlines()
    cells = lines[2].split(",")
    cells[5] = ""
    lines[2] = ",".join(cells)
    (src["dir"] / "demand.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    p = build(src)
    assert p.returncode != 0
    assert P.run_results(P.Path(src["target"]))["tests_fail"] >= 1


def test_snapshot_keeps_history_when_usgs_revises(src):
    """규모가 4.5 → 4.8 로 고쳐지면: 옛 판은 닫히고(valid_to), 새 판이 열린다. 안 바뀐 지진은 한 판 그대로"""
    assert build(src).returncode == 0
    assert q(src, "select count(*), count(dbt_valid_to) from snap_quakes")[0] == (3, 0)
    write_quakes(src["dir"] / "quakes.csv", [
        quake("a1", 4.8, "2025-03-05T00:00:00", "reviewed"), quake("a2", 5.0, "2025-03-01T01:00:00", "reviewed"),
        quake("a3", 4.1, "2025-03-01T01:00:00", place="90 km SSE of Tateyama, Japan")])
    assert build(src).returncode == 0
    hist = q(src, "select mag, status, dbt_valid_to is null from snap_quakes where quake_id = 'a1' order by dbt_valid_from")
    assert hist == [(4.5, "automatic", False), (4.8, "reviewed", True)]
    assert q(src, "select count(*) from snap_quakes where quake_id = 'a2'")[0][0] == 1
    # 같은 원본으로 한 번 더 돌려도 판이 늘지 않는다 (멱등)
    assert build(src).returncode == 0
    assert q(src, "select count(*) from snap_quakes")[0][0] == 4
    # "3월 2일에는 a1 을 얼마로 알고 있었나" 를 되물을 수 있다
    asof = q(src, "select mag from snap_quakes where quake_id = 'a1' and dbt_valid_from <= timestamp '2025-03-02' and (dbt_valid_to > timestamp '2025-03-02' or dbt_valid_to is null)")
    assert asof == [(4.5,)]


def test_history_survives_a_fresh_database(src, tmp_path):
    """CI 처럼 매번 빈 DB 에서 시작해도, 저장해 둔 이력 파일에서 이어서 쌓인다"""
    state = tmp_path / "state"
    assert build(src).returncode == 0
    assert P.save_state(src["db"], state) == 3
    first = (state / "snap_quakes.parquet").read_bytes()
    P.save_state(src["db"], state)
    assert (state / "snap_quakes.parquet").read_bytes() == first          # 같은 내용이면 같은 파일
    P.Path(src["db"]).unlink()                                            # 다음 날: 빈 DB
    write_quakes(src["dir"] / "quakes.csv", [
        quake("a1", 4.8, "2025-03-05T00:00:00", "reviewed"), quake("a2", 5.0, "2025-03-01T01:00:00", "reviewed"),
        quake("a3", 4.1, "2025-03-01T01:00:00", place="90 km SSE of Tateyama, Japan")])
    assert P.restore_state(src["db"], state) == 3
    assert build(src).returncode == 0
    assert q(src, "select mag from snap_quakes where quake_id = 'a1' order by dbt_valid_from") == [(4.5,), (4.8,)]
    assert P.save_state(src["db"], state) == 4
    assert P.restore_state(str(tmp_path / "other.duckdb"), tmp_path / "no-state") == 0
    # 처음 실행: DB 폴더가 아직 없어도 되살리기가 된다 (CI 의 Airflow 실행에서 실제로 났던 실패)
    assert P.restore_state(str(tmp_path / "fresh" / "target" / "wh.duckdb"), state) == 4


def test_map_to_data_year():
    assert P.map_to_data_year("2026-11-12") == "2025-11-12"
    assert P.map_to_data_year("2028-02-29") == "2025-02-28"
    assert P.map_to_data_year("2025-03-01") == "2025-03-01"


MONTHLY = "select month_kst, region, quakes, max_mag, mean_depth_km from fct_quakes_monthly order by 1, 2"


def test_incremental_monthly_equals_full_rebuild(src, tmp_path):
    """증분으로 이어 쌓은 결과와, 같은 원본으로 처음부터 다시 만든 결과가 같아야 한다"""
    assert build(src).returncode == 0
    before = q(src, MONTHLY)
    assert before == [(date(2025, 3, 1), "Japan", 1, 4.1, 10.0), (date(2025, 3, 1), "South Korea", 2, 5.0, 10.0)]
    # 다음 날: 예전 지진 하나가 고쳐지고(4.5→5.6), 새 달의 지진이 하나 들어옴
    new = quake("b1", 6.2, "2025-04-03T00:00:00", "reviewed", "70 km E of Hualien, Taiwan")
    new[1], new[2] = "2025-04-02T03:00:00Z", "2025-04-02 12:00:00"
    write_quakes(src["dir"] / "quakes.csv", [
        quake("a1", 5.6, "2025-03-05T00:00:00", "reviewed"), quake("a2", 5.0, "2025-03-01T01:00:00", "reviewed"),
        quake("a3", 4.1, "2025-03-01T01:00:00", place="90 km SSE of Tateyama, Japan"), new])
    p = build(src)
    assert p.returncode == 0, p.stdout[-1500:]
    inc = q(src, MONTHLY)
    assert (date(2025, 3, 1), "South Korea", 2, 5.6, 10.0) in inc and (date(2025, 4, 1), "Taiwan", 1, 6.2, 10.0) in inc
    full = dict(src, db=str(tmp_path / "full.duckdb"), target=str(tmp_path / "full_target"))
    assert build(full).returncode == 0
    assert inc == q(full, MONTHLY)
    # 바뀐 게 없으면 증분 실행은 아무 것도 건드리지 않는다
    assert build(src).returncode == 0 and q(src, MONTHLY) == inc


def test_incremental_drift_is_caught_by_reconciliation(src):
    """원본에서 지진이 빠지면 증분 집계에는 옛 값이 남는다 — 합계 대조 테스트가 이를 잡아야 한다"""
    assert build(src).returncode == 0
    write_quakes(src["dir"] / "quakes.csv", [
        quake("a2", 5.0, "2025-03-01T01:00:00", "reviewed"),
        quake("a3", 4.1, "2025-03-01T01:00:00", place="90 km SSE of Tateyama, Japan")])
    p = build(src)
    assert p.returncode != 0
    assert "assert_quakes_monthly_matches_source" in P.run_results(P.Path(src["target"]))["failed"]
    assert build(src, "--full-refresh").returncode == 0          # 처음부터 다시 만들면 맞춰진다


def test_export_is_idempotent_and_partitioned(src):
    assert build(src).returncode == 0
    out = src["dir"] / "exports"
    a = P.export_day("2025-03-02", src["db"], out)
    b = P.export_day("2025-03-02", src["db"], out)
    assert a["rows"] == 24 and a["sha"] == b["sha"]
    files = sorted(p.name for p in (out / "fct_demand_hourly" / "demand_date=2025-03-02").iterdir())
    assert files == ["part.parquet"]                       # 임시 파일이 남지 않는다
    back = duckdb.sql(f"select count(*), min(hour_ending), max(hour_ending) from '{a['path']}'").fetchall()[0]
    assert back == (24, 1, 24)


def test_export_of_absent_day_writes_nothing(src):
    assert build(src).returncode == 0
    e = P.export_day("2025-12-25", src["db"], src["dir"] / "exports")
    assert e == {"day": "2025-12-25", "rows": 0, "path": None, "sha": None}
    assert not (src["dir"] / "exports" / "fct_demand_hourly" / "demand_date=2025-12-25").exists()


def test_export_rejects_non_date():
    with pytest.raises(ValueError):
        P.export_day("2025-03-02'; drop table x; --", "nope.duckdb", P.Path("x"))


def test_check_sources_reports_missing_column(src):
    assert P.check_sources(src["vars"])["demand_csv"]["rows"] == 3
    (src["dir"] / "weather.csv").write_text("time,서울\n2025-03-01T00:00,5\n", encoding="utf-8")
    with pytest.raises(P.SourceError, match="mean"):
        P.check_sources(src["vars"])
    with pytest.raises(P.SourceError, match="파일 없음"):
        P.check_sources({**src["vars"], "quakes_csv": str(src["dir"] / "none.csv")})


def test_run_history_replaces_same_date(tmp_path):
    h = tmp_path / "history.csv"
    P.record_run(h, {"logical_date": "2025-03-02", "status": "failed", "run_at_utc": "x"})
    P.record_run(h, {"logical_date": "2025-03-01", "status": "success", "run_at_utc": "y"})
    P.record_run(h, {"logical_date": "2025-03-02", "status": "success", "run_at_utc": "z"})
    rows = list(csv.DictReader(h.open(encoding="utf-8")))
    assert [(r["logical_date"], r["status"]) for r in rows] == [("2025-03-01", "success"), ("2025-03-02", "success")]


def test_daterange():
    assert list(P.daterange("2025-02-27", "2025-03-01")) == ["2025-02-27", "2025-02-28", "2025-03-01"]
    with pytest.raises(ValueError):
        list(P.daterange("2025-03-02", "2025-03-01"))


def test_lineage_and_report(src, tmp_path):
    assert build(src).returncode == 0
    manifest = json.loads((P.Path(src["target"]) / "manifest.json").read_text(encoding="utf-8"))
    nodes, edges = lineage(manifest)
    name = {n["id"]: n["name"] for n in nodes}
    pairs = {(name[a], name[b]) for a, b in edges}
    assert ("demand.csv", "stg_demand_wide") in pairs and ("int_demand_hourly", "fct_demand_hourly") in pairs
    assert ("stg_quakes", "snap_quakes") in pairs
    layer = {n["name"]: n["layer"] for n in nodes}
    assert layer["demand.csv"] < layer["stg_demand_wide"] < layer["int_demand_hourly"] < layer["fct_demand_hourly"] < layer["fct_demand_daily"]
    root = tmp_path / "proj"
    (root / "target").mkdir(parents=True)
    for f in ("manifest.json", "run_results.json"):
        shutil.copy(P.Path(src["target"]) / f, root / "target" / f)
    out = build_report(root)
    text = out.read_text(encoding="utf-8")
    assert "fct_demand_daily" in text and "아직 기록 없음" in text and "<svg" in text


def test_dag_file_is_valid_python_and_names_tasks():
    code = (P.ROOT / "dags" / "warehouse_daily.py").read_text(encoding="utf-8")
    compile(code, "warehouse_daily.py", "exec")
    for t in ("collect_jobs", "check_sources", "dbt_build", "export_partition", "record", "report"):
        assert f"def {t}(" in code


# ---------- 채용 공고

def test_job_marts(src):
    assert build(src).returncode == 0
    rows = q(src, "select job_key, is_tech, skill_count, salary_quality, salary_mid_usd from fct_job_postings order by 1")
    assert rows == [("arbeitnow:be-dev-1", True, 2, "none", None), ("arbeitnow:koch-2", False, 0, "none", None),
                    ("remoteok:1", True, 4, "annual", 110000.0), ("remoteok:2", False, 0, "suspect_low", None)]
    # 2025-03-03 이 속한 주: 기술 공고 1건(백엔드), 그 전 주: 1건(데이터 엔지니어)
    wk = q(src, "select week_start, skill, postings, tech_postings, share_of_tech from fct_skill_demand_weekly where skill = 'Python' order by 1")
    assert wk == [(date(2025, 2, 24), "Python", 1, 1, 1.0), (date(2025, 3, 3), "Python", 1, 1, 1.0)]
    assert q(src, "select postings from dim_skill where skill = 'dbt'")[0][0] == 1
    assert q(src, "select sum(postings), sum(tech_postings), sum(with_suspect_salary) from fct_jobs_daily")[0] == (4, 2, 1)


def test_skill_outside_dictionary_fails(src):
    """사전에 없는 기술 이름이 공고에 붙어 있으면 빌드가 실패해야 한다"""
    ex = J.load(P.Path(src["vars"]["jobs_csv"]))
    J.merge(ex, [job("remoteok", "9", "COBOL Developer", "2025-03-04T00:00:00Z", "COBOL")], "2025-03-11", "v1")
    J.save(ex, P.Path(src["vars"]["jobs_csv"]))
    assert build(src).returncode != 0
    assert "assert_job_skills_in_dictionary" in P.run_results(P.Path(src["target"]))["failed"]


def test_find_skills_title_and_body():
    rules, version = J.load_skill_dict()
    assert len(version) == 8
    f = lambda t, b="": J.find_skills(t, b, rules).split("|")
    assert f("Senior Data Engineer", "<p>We use <b>Python</b>, dbt and Airflow on AWS.</p>") == ["AWS", "Airflow", "Data Engineer (role)", "Python", "dbt"]
    assert "Java" not in f("JavaScript Developer") and "JavaScript" in f("JavaScript Developer")
    assert "Java" in f("Java Engineer") and "JavaScript" not in f("Java Engineer")
    assert f("Barista", "Go to our store. Scalable team. Spring is coming. Swift code required for transfer.") == [""]
    assert "Go" in f("Golang Developer") and "Scala" in f("Scala Engineer") and "Spring" in f("Dev", "Spring Boot services")
    # 직무 이름은 제목에서만: 본문에 'frontend' 가 나와도 프런트엔드 공고가 아니다
    assert "Frontend (role)" not in f("Data Analyst", "works with the frontend team")
    assert "C++" in f("Embedded C++ Engineer") and "C#/.NET" in f(".NET Developer")


def test_fix_mojibake():
    assert J.fix_mojibake("Engineer â\x80\x94 Kubernetes") == "Engineer — Kubernetes"
    assert J.fix_mojibake("Teilzeitkraft Küche") == "Teilzeitkraft Küche"          # 정상 문자열은 그대로
    assert J.fix_mojibake("Ã¼ber") == "über" and J.fix_mojibake("") == ""


def fake_feeds(pages):
    """Arbeitnow 쪽별 응답과 Remote OK 응답을 흉내 냄"""
    calls = []

    def get(url):
        calls.append(url)
        if "remoteok" in url:
            return [{"legal": "x"}, {"id": "1", "position": "Data Engineer", "company": "A", "epoch": 1741000000, "salary_min": 90000,
                                     "salary_max": 120000, "url": "https://remoteOK.com/j/1", "description": "<p>Python and SQL</p>", "tags": ["golang"]}]
        n = int(url.split("page=")[1])
        return {"data": pages[n - 1] if n <= len(pages) else []}
    return get, calls


def arb(slug, ts=1741000000):
    return {"slug": slug, "title": "Dev " + slug, "company_name": "B", "remote": False, "created_at": ts, "url": "https://x/" + slug, "description": "Kotlin"}


def test_collect_stops_at_overlap_and_is_idempotent(tmp_path, monkeypatch):
    jp, lp = tmp_path / "jobs.csv", tmp_path / "log.csv"
    get, calls = fake_feeds([[arb("a"), arb("b")], [arb("b"), arb("c")], [arb("d")], [arb("e")]])
    res = {e["source"]: e for e in J.collect("2025-03-11", jp, lp, get, pause=0)}
    assert res["arbeitnow"]["pages"] == 3 and res["arbeitnow"]["new"] == 4 and res["arbeitnow"]["overlap"] == "first_run"   # 처음: 3쪽까지만
    assert res["remoteok"]["new"] == 1
    rows = J.load(jp)
    assert rows[("remoteok", "1")]["skills"] == "Data Engineer (role)|Python|SQL"                    # 엉뚱한 태그(golang)는 쓰지 않음
    assert rows[("remoteok", "1")]["url"] == "https://remoteok.com/j/1" and "description" not in rows[("remoteok", "1")]
    first = jp.read_bytes()
    J.collect("2025-03-11", jp, lp, get, pause=0)
    assert jp.read_bytes() == first                                              # 같은 날 다시 돌려도 같은 파일
    log = {r["source"]: r for r in csv.DictReader(lp.open(encoding="utf-8"))}
    assert log["arbeitnow"]["new"] == "4" and log["arbeitnow"]["overlap"] == "first_run"   # 다시 돌려도 그날 기록이 지워지지 않음
    # 다음 날: 새 공고 z 가 맨 앞에 오고, 1쪽에서 이미 아는 a 를 만나 멈춘다
    get2, calls2 = fake_feeds([[arb("z"), arb("a")], [arb("b")]])
    res2 = {e["source"]: e for e in J.collect("2025-03-12", jp, lp, get2, pause=0)}
    assert res2["arbeitnow"]["pages"] == 1 and res2["arbeitnow"]["new"] == 1 and res2["arbeitnow"]["overlap"] == "yes"
    rows = J.load(jp)
    assert rows[("arbeitnow", "a")]["first_seen"] == "2025-03-11" and rows[("arbeitnow", "a")]["last_seen"] == "2025-03-12"
    assert rows[("arbeitnow", "c")]["last_seen"] == "2025-03-11"


def test_collect_reports_gap_and_survives_failure(tmp_path):
    jp, lp = tmp_path / "jobs.csv", tmp_path / "log.csv"
    get, _ = fake_feeds([[arb("a")]])
    J.collect("2025-03-11", jp, lp, get, pause=0)
    # 오래 쉬었다 돌린 경우: 8쪽을 넘겨도 아는 공고가 안 나옴 → 빈틈(no)
    get2, calls = fake_feeds([[arb(f"n{i}")] for i in range(12)])
    res = {e["source"]: e for e in J.collect("2025-03-20", jp, lp, get2, pause=0)}
    assert res["arbeitnow"]["overlap"] == "no" and res["arbeitnow"]["pages"] == J.MAX_PAGES

    def broken(url):
        if "arbeitnow" in url:
            raise TimeoutError("timeout")
        return [{"legal": "x"}]
    res = {e["source"]: e for e in J.collect("2025-03-21", jp, lp, broken, pause=0)}
    assert res["arbeitnow"]["overlap"] == "error:TimeoutError" and res["remoteok"]["fetched"] == 0
    assert len(J.load(jp)) == 2 + 8                                              # 실패해도 모아 둔 공고는 그대로


def test_content_change_is_recorded(tmp_path):
    ex = {}
    J.merge(ex, [job("remoteok", "1", "Data Engineer", "2025-03-01T00:00:00Z", "", 90000, 120000)], "2025-03-11", "v1")
    st = J.merge(ex, [job("remoteok", "1", "Data Engineer", "2025-03-01T00:00:00Z", "", 100000, 130000)], "2025-03-12", "v1")
    r = ex[("remoteok", "1")]
    assert st["changed"] == 1 and r["changed_on"] == "2025-03-12" and r["salary_min"] == 100000 and r["first_seen"] == "2025-03-11"
    assert J.merge(ex, [job("remoteok", "1", "Data Engineer", "2025-03-01T00:00:00Z", "", 100000, 130000)], "2025-03-13", "v1")["changed"] == 0
