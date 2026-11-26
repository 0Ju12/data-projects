import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest

from status import collect

NOW = datetime(2026, 11, 25, 3, 0, tzinfo=timezone.utc)


def run(i, conclusion="success", status="completed", minutes=2, ago_h=0):
    t = NOW - timedelta(hours=ago_h)
    return {
        "id": i,
        "run_number": i,
        "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "event": "schedule",
        "created_at": t.isoformat().replace("+00:00", "Z"),
        "run_started_at": t.isoformat().replace("+00:00", "Z"),
        "updated_at": (t + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z"),
        "html_url": f"https://gh/runs/{i}",
        "display_title": f"run {i}",
    }


class FakeAPI:
    """경로 → 응답. 요청을 기록해 알림 흐름을 확인."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, req, timeout=0):
        u = urlparse(req.full_url)
        key = (req.get_method(), u.path)
        body = json.loads(req.data) if req.data else None
        self.calls.append((key[0], key[1], body, u.query))
        val = self.routes.get(key, self.routes.get(u.path))
        if val is None:
            raise OSError(f"no route {key}")
        data = val(body) if callable(val) else val

        class R:
            def read(self_):
                return json.dumps(data).encode()

            def __enter__(self_):
                return self_

            def __exit__(self_, *a):
                return False

        return R()


def gh_routes():
    R = "/repos/o/r"
    return {
        f"{R}/actions/workflows": {
            "workflows": [
                {"id": 1, "name": "geo daily update", "path": ".github/workflows/geo-daily.yml", "state": "active"},
                {"id": 2, "name": "tests", "path": ".github/workflows/tests.yml", "state": "active"},
                {"id": 3, "name": "old", "path": ".github/workflows/old.yml", "state": "disabled_manually"},
            ]
        },
        f"{R}/actions/workflows/1/runs": {
            "workflow_runs": [
                run(10, minutes=3),
                run(9, "failure", ago_h=24),
                run(8, "cancelled", ago_h=48),
                run(7, minutes=1, ago_h=72),
            ]
        },
        f"{R}/actions/workflows/2/runs": {
            "workflow_runs": [
                run(20, status="in_progress"),
                run(19, "failure"),
                run(18, "failure", ago_h=1),
                run(17, ago_h=2),
            ]
        },
        f"{R}/actions/runs/10/jobs": {
            "jobs": [
                {
                    "id": 100,
                    "name": "update",
                    "conclusion": "success",
                    "html_url": "https://gh/j/100",
                    "steps": [{"name": "산불 갱신", "conclusion": "success"}],
                }
            ]
        },
        f"{R}/actions/runs/19/jobs": {
            "jobs": [
                {
                    "id": 190,
                    "name": "test (krgeo)",
                    "conclusion": "failure",
                    "html_url": "https://gh/j/190",
                    "steps": [{"name": "pytest", "conclusion": "failure"}],
                }
            ]
        },
        f"{R}/check-runs/100/annotations": [
            {"annotation_level": "failure", "message": "Process completed with exit code 1."},
            {"annotation_level": "warning", "message": "Node 16 deprecated"},
        ],
    }


def test_summarize_runs_rate_streak_and_median():
    runs = [collect._run(r) for r in [run(3, "failure"), run(2, "failure"), run(1, minutes=4), run(0, "cancelled")]]
    s = collect.summarize_runs(runs)
    assert (
        s["failure_streak"] == 2
        and s["success_rate"] == pytest.approx(1 / 3, abs=1e-3)
        and s["median_duration_s"] == 240
    )
    assert s["last_success_at"] == runs[2]["created_at"]


def test_collect_actions_finds_hidden_failure_via_annotation_and_real_failure():
    gh = collect.GitHub("o/r", opener=FakeAPI(gh_routes()))
    wfs = collect.collect_actions(gh)
    assert [w["name"] for w in wfs] == ["geo daily update", "tests"]  # 꺼진 워크플로는 뺌
    geo, tests = wfs
    assert geo["failure_streak"] == 0 and geo["success_rate"] == pytest.approx(2 / 3, abs=1e-3)
    assert geo["failed_steps"] == [
        {
            "job": "update",
            "step": "Process completed with exit code 1.",
            "hidden": True,
            "url": "https://gh/j/100",
            "source": "annotation",
        }
    ]
    assert (
        tests["failure_streak"] == 2 and tests["last"]["status"] == "in_progress" and tests["steps_checked_run"] == 19
    )
    assert tests["failed_steps"][0]["hidden"] is False


def test_step_outcomes_from_workflow_context(monkeypatch):
    env = json.dumps(
        {
            "fire": {"outcome": "failure", "conclusion": "success", "outputs": {}},
            "warehouse": {"outcome": "success", "conclusion": "success", "outputs": {}},
        }
    )
    monkeypatch.setenv("GITHUB_JOB", "update")
    out = collect.step_outcomes(env, "geo daily update", "u")
    assert out == [
        {
            "workflow": "geo daily update",
            "job": "update",
            "step": "fire",
            "hidden": True,
            "url": "u",
            "source": "outcome",
        }
    ]
    assert collect.step_outcomes("not json", "x") == [] and collect.step_outcomes(None, "x") == []


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_freshness_states_timezones_and_row_checks(tmp_path):
    write(tmp_path / "a.json", json.dumps({"updated": "2026-11-25 01:00"}))  # UTC, 2시간 전
    write(
        tmp_path / "b.json", json.dumps({"updated": "2026-11-22", "fetch": {"N20": 3, "SNPP": 0, "weather": "ok"}})
    )  # KST 날짜
    write(
        tmp_path / "c.csv",
        "run_at_utc,status,tests_fail\n2026-11-24T05:00:00Z,success,0\n2026-11-25T02:30:00Z,failed,2\n",
    )
    write(tmp_path / "d.csv", "area,month\nKR,2026-08-01\nKR,2026-09-01\n")
    write(tmp_path / "e.json", json.dumps({"built": "2026-11-24 15:07 KST"}))
    checks = [
        {"id": "a", "name": "A", "path": "a.json", "kind": "json", "key": "updated", "tz": "UTC", "max_age_h": 30},
        {
            "id": "b",
            "name": "B",
            "path": "b.json",
            "kind": "json",
            "key": "updated",
            "tz": "KST",
            "max_age_h": 48,
            "partial": {"key": "fetch", "zero_is_warn": ["N20", "SNPP"], "ok_values": {"weather": "ok"}},
        },
        {
            "id": "c",
            "name": "C",
            "path": "c.csv",
            "kind": "csv_last",
            "key": "run_at_utc",
            "tz": "UTC",
            "max_age_h": 30,
            "row_checks": {"status": "success", "tests_fail": "0"},
        },
        {"id": "d", "name": "D", "path": "d.csv", "kind": "csv_max", "key": "month", "tz": "UTC", "max_age_h": 3600},
        {"id": "e", "name": "E", "path": "e.json", "kind": "json", "key": "built", "tz": "KST", "max_age_h": None},
        {"id": "f", "name": "F", "path": "nope.json", "kind": "json", "key": "x", "tz": "UTC", "max_age_h": 1},
    ]
    f = {r["id"]: r for r in collect.freshness(tmp_path, checks, NOW)}
    assert f["a"]["state"] == "ok" and f["a"]["age_h"] == 2.0
    assert (
        f["b"]["state"] == "stale" and f["b"]["age_h"] == 84.0 and f["b"]["warnings"] == ["받은 건수 0: SNPP"]
    )  # 11-22 00:00 KST = 11-21 15:00 UTC → 84시간
    assert f["c"]["state"] == "fail" and len(f["c"]["warnings"]) == 2
    assert f["d"]["state"] == "ok" and f["e"]["state"] == "manual" and f["f"]["state"] == "missing"
    probs = collect.problems([], list(f.values()))
    levels = {p["key"]: p["level"] for p in probs}
    assert levels["stale:b"] == "fail" and levels["check:c"] == "fail" and levels["missing:f"] == "fail"
    assert levels["partial:b:받은 건수 0: SNPP"] == "warn" and collect.overall(probs) == "fail"


def test_build_with_api_error_still_reports_freshness(tmp_path):
    def broken(req, timeout=0):
        raise OSError("blocked")

    rep = collect.build("o/r", collect.GitHub("o/r", opener=broken), now=NOW)
    assert rep["workflows"] == [] and "blocked" in rep["api_error"] and rep["freshness"]


def test_alert_opens_updates_and_closes_issue():
    issues = []

    def list_issues(_):
        return [i for i in issues if i["state"] == "open"]

    def create(body):
        issues.append({"number": 1, "state": "open", **body})
        return issues[-1]

    def patch(body):
        issues[0].update(body)
        return issues[0]

    R = "/repos/o/r"
    api = FakeAPI(
        {
            ("GET", f"{R}/issues"): list_issues,
            ("POST", f"{R}/issues"): create,
            ("PATCH", f"{R}/issues/1"): patch,
            ("POST", f"{R}/issues/1/comments"): lambda b: {"id": 5},
        }
    )
    gh = collect.GitHub("o/r", "tok", opener=api)
    p1 = [
        {"level": "fail", "key": "stale:fire", "text": "산불 늦음", "url": None},
        {"level": "warn", "key": "w", "text": "주의", "url": None},
    ]
    assert collect.alert(gh, p1, "https://page", NOW) == "opened"
    assert (
        issues[0]["labels"] == ["pipeline-alert"] and "산불 늦음" in issues[0]["body"] and "주의" in issues[0]["body"]
    )
    assert collect.alert(gh, p1, "https://page", NOW) == "unchanged"  # 같은 문제면 다시 쓰지 않음
    p2 = p1 + [{"level": "fail", "key": "wf:x", "text": "테스트 실패", "url": "u"}]
    assert collect.alert(gh, p2, None, NOW) == "updated" and issues[0]["title"] == "파이프라인 경보: 문제 2건"
    assert collect.alert(gh, [p1[1]], None, NOW) == "closed" and issues[0]["state"] == "closed"  # 경고만 남으면 닫음
    assert collect.alert(gh, [], None, NOW) == "ok"
    assert all(("Authorization" not in str(c)) for c in api.calls)


def test_repo_sources_config_reads_real_outputs():
    checks = json.loads((collect.HERE / "sources.json").read_text(encoding="utf-8"))["checks"]
    rows = collect.freshness(collect.ROOT, checks, NOW)
    assert all(r["state"] != "missing" for r in rows), [r for r in rows if r["state"] == "missing"]
