"""파이프라인 상태 수집 → docs/status.json (+ 선택: 문제를 GitHub 이슈 하나로 알림).

    python -m status.collect --repo 0Ju12/data-projects            # GITHUB_TOKEN 있으면 사용 (없어도 공개 저장소는 됨)
    python -m status.collect --repo 0Ju12/data-projects --alert    # 문제가 있으면 이슈 열기/고치기, 없어지면 닫기

보는 것
1. 워크플로마다 main 의 최근 실행 30번: 성공률, 걸린 시간 중앙값, 연속 실패, 마지막 성공 시각
2. 숨은 실패: continue-on-error 단계가 실패해도 작업(job)은 '성공' 으로 끝나고 API 의 단계 결과도 'success' 가 된다
   → 성공한 작업의 실패 주석(annotation)을 보고, 워크플로 안에서 돌 때는 steps.*.outcome 을 직접 받음
3. 산출물 신선도: 프로젝트마다 남기는 갱신 시각을 읽어 기준 시간(max_age_h)과 비교
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DOCS = HERE.parent / "docs"
API = "https://api.github.com"
KST = timezone(timedelta(hours=9))
TZ = {"UTC": timezone.utc, "KST": KST}
LABEL = "pipeline-alert"
RUNS = 30


# ── GitHub API ──────────────────────────────────────────────────────────
class GitHub:
    def __init__(self, repo: str, token: str | None = None, opener=urllib.request.urlopen):
        self.repo, self.token, self.opener = repo, token, opener

    def request(self, method: str, path: str, body: dict | None = None):
        url = path if path.startswith("http") else f"{API}{path}"
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "pipeline-status")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        with self.opener(req, timeout=30) as r:
            return json.loads(r.read() or b"null")

    def get(self, path: str):
        return self.request("GET", path)


def parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _run(r: dict) -> dict:
    start, end = parse_time(r.get("run_started_at") or r.get("created_at")), parse_time(r.get("updated_at"))
    done = r.get("status") == "completed"
    return {
        "id": r["id"],
        "number": r.get("run_number"),
        "status": r.get("status"),
        "conclusion": r.get("conclusion"),
        "event": r.get("event"),
        "created_at": r.get("created_at"),
        "url": r.get("html_url"),
        "duration_s": round((end - start).total_seconds()) if done and start and end else None,
        "title": (r.get("display_title") or "")[:120],
    }


def summarize_runs(runs: list[dict]) -> dict:
    """최근 실행(최신이 앞) → 성공률·연속 실패·마지막 성공. 취소·건너뜀은 성공률에서 뺌."""
    done = [r for r in runs if r["status"] == "completed" and r["conclusion"] not in ("cancelled", "skipped")]
    ok = [r for r in done if r["conclusion"] == "success"]
    streak = 0
    for r in done:
        if r["conclusion"] == "success":
            break
        streak += 1
    durs = [r["duration_s"] for r in ok if r["duration_s"] is not None]
    return {
        "completed": len(done),
        "success_rate": round(len(ok) / len(done), 3) if done else None,
        "failure_streak": streak,
        "median_duration_s": round(statistics.median(durs)) if durs else None,
        "last_success_at": ok[0]["created_at"] if ok else None,
        "last": runs[0] if runs else None,
    }


def hidden_failures(jobs: list[dict], annotations: dict[int, list[dict]] | None = None) -> list[dict]:
    """실패한 단계 목록. hidden=True 는 작업(job)이 '성공' 으로 끝났는데 안에서 실패가 있었던 것.

    continue-on-error 단계는 실패해도 API 의 단계 conclusion 이 'success' 로 바뀌어 단계만 봐서는 안 보인다
    → 성공한 작업의 실패 주석(annotation, "Process completed with exit code 1" 등)을 함께 본다."""
    out = []
    for j in jobs:
        for s in j.get("steps") or []:
            if s.get("conclusion") == "failure":
                out.append(
                    {
                        "job": j.get("name"),
                        "step": s.get("name"),
                        "hidden": j.get("conclusion") == "success",
                        "url": j.get("html_url"),
                        "source": "step",
                    }
                )
        if j.get("conclusion") == "success":
            for a in (annotations or {}).get(j.get("id"), []):
                if a.get("annotation_level") == "failure":
                    out.append(
                        {
                            "job": j.get("name"),
                            "step": (a.get("title") or a.get("message") or "")[:160],
                            "hidden": True,
                            "url": j.get("html_url"),
                            "source": "annotation",
                        }
                    )
    return out


def step_outcomes(env_json: str | None, workflow: str, run_url: str | None = None) -> list[dict]:
    """워크플로 안에서 실행할 때 STEP_OUTCOMES='${{ toJSON(steps) }}' 로 받은 단계 결과.
    outcome(continue-on-error 적용 전)이 failure 인데 conclusion 이 success 면 숨은 실패."""
    if not env_json:
        return []
    try:
        steps = json.loads(env_json)
    except json.JSONDecodeError:
        return []
    return [
        {
            "workflow": workflow,
            "job": os.environ.get("GITHUB_JOB", ""),
            "step": sid,
            "hidden": True,
            "url": run_url,
            "source": "outcome",
        }
        for sid, v in steps.items()
        if isinstance(v, dict) and v.get("outcome") == "failure" and v.get("conclusion") == "success"
    ]


def collect_actions(gh: GitHub, branch: str = "main", now: datetime | None = None) -> list[dict]:
    out = []
    for wf in gh.get(f"/repos/{gh.repo}/actions/workflows?per_page=100")["workflows"]:
        if wf.get("state") != "active":
            continue
        raw = gh.get(
            f"/repos/{gh.repo}/actions/workflows/{wf['id']}/runs?branch={branch}&per_page={RUNS}&exclude_pull_requests=true"
        )["workflow_runs"]
        runs = [_run(r) for r in raw]
        s = summarize_runs(runs)
        steps = []
        last_done = next(
            (r for r in runs if r["status"] == "completed" and r["conclusion"] not in ("cancelled", "skipped")), None
        )
        if last_done:
            jobs = gh.get(f"/repos/{gh.repo}/actions/runs/{last_done['id']}/jobs?per_page=100")["jobs"]
            ann = {}
            for j in [j for j in jobs if j.get("conclusion") == "success"][:20]:
                try:
                    ann[j["id"]] = gh.get(f"/repos/{gh.repo}/check-runs/{j['id']}/annotations?per_page=50")
                except Exception:
                    pass
            steps = hidden_failures(jobs, ann)
        out.append(
            {
                "id": wf["id"],
                "name": wf["name"],
                "path": wf["path"],
                "url": wf.get("html_url"),
                **s,
                "runs": runs,
                "steps_checked_run": last_done["id"] if last_done else None,
                "failed_steps": steps,
            }
        )
    return sorted(out, key=lambda w: w["name"].lower())


# ── 산출물 신선도 ─────────────────────────────────────────────────────────
def _read_time(root: Path, c: dict) -> tuple[str | None, dict]:
    p = root / c["path"]
    if not p.exists():
        return None, {}
    if c["kind"] == "json":
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get(c["key"]), d
    with p.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None, {}
    if c["kind"] == "csv_last":
        return rows[-1].get(c["key"]), rows[-1]
    return max(r[c["key"]] for r in rows if r.get(c["key"])), {}


def to_dt(value: str, tz: str) -> datetime:
    v = value.replace(" KST", "").replace("Z", "+00:00").strip()
    dt = datetime.fromisoformat(v)
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ[tz])


def freshness(root: Path, checks: list[dict], now: datetime) -> list[dict]:
    out = []
    for c in checks:
        raw, ctx = _read_time(root, c)
        row = {
            "id": c["id"],
            "name": c["name"],
            "path": c["path"],
            "page": c.get("page"),
            "max_age_h": c.get("max_age_h"),
            "note": c.get("note"),
            "last": raw,
            "age_h": None,
            "state": "missing",
            "warnings": [],
        }
        if raw:
            dt = to_dt(raw, c["tz"])
            row["last_utc"] = dt.astimezone(timezone.utc).isoformat()
            row["age_h"] = round((now - dt).total_seconds() / 3600, 1)
            if c.get("max_age_h") is None:
                row["state"] = "manual"
            else:
                row["state"] = "ok" if row["age_h"] <= c["max_age_h"] else "stale"
        for k, want in (c.get("row_checks") or {}).items():
            if str(ctx.get(k)) != want:
                row["warnings"].append(f"{k} = {ctx.get(k)} (기대 {want})")
                row["state"] = "fail"
        part = c.get("partial")
        if part and isinstance(ctx.get(part["key"]), dict):
            got = ctx[part["key"]]
            zeros = [k for k in part.get("zero_is_warn", []) if got.get(k) == 0]
            if zeros:
                row["warnings"].append("받은 건수 0: " + ", ".join(zeros))
            for k, v in (part.get("ok_values") or {}).items():
                if got.get(k) != v:
                    row["warnings"].append(f"{k} = {got.get(k)}")
        out.append(row)
    return out


# ── 문제 정리 ───────────────────────────────────────────────────────────
def problems(workflows: list[dict], fresh: list[dict]) -> list[dict]:
    """level: fail (알림 이슈를 엶) / warn (이슈 본문에만)."""
    out = []
    for w in workflows:
        last = w.get("last") or {}
        if w["failure_streak"]:
            out.append(
                {
                    "level": "fail",
                    "key": f"wf:{w['path']}",
                    "text": f"워크플로 '{w['name']}' 최근 {w['failure_streak']}번 연속 실패",
                    "url": next(
                        (
                            r["url"]
                            for r in w["runs"]
                            if r["conclusion"] not in (None, "success", "cancelled", "skipped")
                        ),
                        w.get("url"),
                    ),
                }
            )
        for s in w["failed_steps"]:
            if s["hidden"]:
                what = {
                    "annotation": f"'{s['job']}' 작업은 성공했지만 실패 기록이 남음: {s['step']}",
                    "outcome": f"이번 실행의 '{s['step']}' 단계가 실패했지만 계속 진행함 (continue-on-error)",
                }.get(s.get("source"), f"'{s['step']}' 단계가 실패했지만 작업은 성공으로 끝남 (continue-on-error)")
                out.append(
                    {
                        "level": "warn",
                        "key": f"step:{w['path']}:{s['job']}:{s['step']}",
                        "text": f"'{w['name']}' — {what}",
                        "url": s["url"],
                    }
                )
        if last.get("status") == "completed" and last.get("conclusion") == "cancelled":
            out.append(
                {
                    "level": "warn",
                    "key": f"cancel:{w['path']}",
                    "text": f"'{w['name']}' 마지막 실행이 취소됨",
                    "url": last.get("url"),
                }
            )
    for f in fresh:
        if f["state"] == "stale":
            out.append(
                {
                    "level": "fail",
                    "key": f"stale:{f['id']}",
                    "text": f"{f['name']} 갱신이 {f['age_h']:.0f}시간 전 (기준 {f['max_age_h']}시간)",
                    "url": None,
                }
            )
        elif f["state"] == "missing":
            out.append(
                {
                    "level": "fail",
                    "key": f"missing:{f['id']}",
                    "text": f"{f['name']} 갱신 시각을 읽지 못함 ({f['path']})",
                    "url": None,
                }
            )
        elif f["state"] == "fail":
            out.append(
                {
                    "level": "fail",
                    "key": f"check:{f['id']}",
                    "text": f"{f['name']}: " + "; ".join(f["warnings"]),
                    "url": None,
                }
            )
        if f["state"] != "fail":
            for wtext in f["warnings"]:
                out.append(
                    {"level": "warn", "key": f"partial:{f['id']}:{wtext}", "text": f"{f['name']}: {wtext}", "url": None}
                )
    return out


def overall(probs: list[dict]) -> str:
    return "fail" if any(p["level"] == "fail" for p in probs) else "warn" if probs else "ok"


# ── 알림 이슈 ───────────────────────────────────────────────────────────
def _fingerprint(probs: list[dict]) -> str:
    return hashlib.sha1("\n".join(sorted(p["key"] for p in probs if p["level"] == "fail")).encode()).hexdigest()[:12]


def issue_body(probs: list[dict], page_url: str | None, now: datetime) -> str:
    lines = [f"파이프라인 상태 점검에서 문제를 찾았습니다 ({now.astimezone(KST):%Y-%m-%d %H:%M} KST).", ""]
    for lvl, head in (("fail", "### 고쳐야 할 것"), ("warn", "### 살펴볼 것")):
        items = [p for p in probs if p["level"] == lvl]
        if items:
            lines += [head, *[f"- {p['text']}" + (f" — [기록]({p['url']})" if p.get("url") else "") for p in items], ""]
    if page_url:
        lines.append(f"상태판: {page_url}")
    lines += [
        "",
        "모든 문제가 없어지면 이 이슈는 자동으로 닫힙니다.",
        f"<!-- pipeline-status fp:{_fingerprint(probs)} -->",
    ]
    return "\n".join(lines)


def alert(gh: GitHub, probs: list[dict], page_url: str | None = None, now: datetime | None = None) -> str:
    """fail 이 있으면 이슈 하나를 열거나(이미 있으면 내용이 바뀔 때만 고치고 댓글), 없으면 열린 이슈를 닫는다."""
    now = now or datetime.now(timezone.utc)
    open_issues = gh.get(f"/repos/{gh.repo}/issues?labels={LABEL}&state=open&per_page=10")
    open_issues = [i for i in open_issues if "pull_request" not in i]
    fails = [p for p in probs if p["level"] == "fail"]
    if not fails:
        for i in open_issues:
            gh.request(
                "POST",
                f"/repos/{gh.repo}/issues/{i['number']}/comments",
                {"body": "다시 점검했더니 모두 정상입니다. 닫습니다."},
            )
            gh.request(
                "PATCH", f"/repos/{gh.repo}/issues/{i['number']}", {"state": "closed", "state_reason": "completed"}
            )
        return "closed" if open_issues else "ok"
    title = f"파이프라인 경보: 문제 {len(fails)}건"
    body = issue_body(probs, page_url, now)
    if not open_issues:
        try:  # 라벨이 없으면 만듦 (이미 있으면 422 → 무시)
            gh.request(
                "POST",
                f"/repos/{gh.repo}/labels",
                {"name": LABEL, "color": "d73a4a", "description": "파이프라인 상태 점검이 연 경보"},
            )
        except Exception:
            pass
        gh.request("POST", f"/repos/{gh.repo}/issues", {"title": title, "body": body, "labels": [LABEL]})
        return "opened"
    i = open_issues[0]
    if f"fp:{_fingerprint(probs)}" in (i.get("body") or ""):
        return "unchanged"
    gh.request("PATCH", f"/repos/{gh.repo}/issues/{i['number']}", {"title": title, "body": body})
    gh.request(
        "POST",
        f"/repos/{gh.repo}/issues/{i['number']}/comments",
        {"body": "문제 목록이 바뀌었습니다:\n\n" + "\n".join(f"- {p['text']}" for p in fails)},
    )
    return "updated"


# ── 실행 ───────────────────────────────────────────────────────────────
def build(repo: str, gh: GitHub | None, root: Path = ROOT, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    checks = json.loads((HERE / "sources.json").read_text(encoding="utf-8"))["checks"]
    fresh = freshness(root, checks, now)
    workflows, api_error = [], None
    if gh:
        try:
            workflows = collect_actions(gh, now=now)
        except Exception as e:  # API 가 막혀도 신선도는 냄
            api_error = f"{type(e).__name__}: {e}"[:300]
    here = step_outcomes(
        os.environ.get("STEP_OUTCOMES"),
        os.environ.get("GITHUB_WORKFLOW", ""),
        f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        if os.environ.get("GITHUB_RUN_ID")
        else None,
    )
    for h in here:
        w = next((w for w in workflows if w["name"] == h["workflow"]), None)
        if w is not None:
            w["failed_steps"].append(h)
    probs = problems(workflows, fresh)
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "repo": repo,
        "overall": overall(probs),
        "problems": probs,
        "workflows": workflows,
        "freshness": fresh,
        "api_error": api_error,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "0Ju12/data-projects"))
    ap.add_argument("--offline", action="store_true", help="GitHub API 없이 신선도만")
    ap.add_argument("--alert", action="store_true", help="문제를 이슈로 알림 (GITHUB_TOKEN 에 issues: write 필요)")
    ap.add_argument("--page-url", default="https://0ju12.github.io/data-projects/status/")
    ap.add_argument("--out", type=Path, default=DOCS / "status.json")
    a = ap.parse_args(argv)
    gh = None if a.offline else GitHub(a.repo, os.environ.get("GITHUB_TOKEN"))
    report = build(a.repo, gh)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        json.dumps(
            {
                "overall": report["overall"],
                "problems": [p["text"] for p in report["problems"]],
                "workflows": len(report["workflows"]),
                "api_error": report["api_error"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    if a.alert:
        if not gh or report["api_error"]:
            print("알림 건너뜀: GitHub API 를 쓰지 못함")
        else:
            print("alert:", alert(gh, report["problems"], a.page_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
