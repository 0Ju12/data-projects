"""채용 공고 수집 — Remote OK · Arbeitnow 공개 피드 (키 없음)

저장하는 것: 제목·회사·지역·원격 여부·게시 시각·급여 범위·원문 링크, 그리고 본문에서 찾은 기술 이름 목록.
공고 본문 자체는 저장하지 않습니다 — 받는 순간 기술 사전(seeds/skills.csv)으로 훑어 이름만 남깁니다.
그래서 사전을 고쳐도 예전 공고는 다시 훑을 수 없고, 어떤 판의 사전으로 뽑았는지(skills_dict)를 행마다 적어 둡니다.
두 피드 모두 "최근 공고 N건"만 주므로, 어제 받은 공고와 겹칠 때까지 쪽을 넘겨 빈틈 없이 잇습니다.

출처 표기(이용 조건): Remote OK https://remoteok.com · Arbeitnow https://www.arbeitnow.com
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
JOBS = ROOT / "data" / "jobs.csv"
FETCH_LOG = ROOT / "data" / "jobs_fetch_log.csv"
UA = "data-projects-warehouse/1.0 (+https://github.com/0Ju12/data-projects)"
FIELDS = ["source", "job_id", "title", "company", "location", "remote", "posted_at_utc", "salary_min", "salary_max",
          "url", "skills", "skills_dict", "content_hash", "first_seen", "last_seen", "changed_on"]
LOG_FIELDS = ["run_date", "source", "fetched", "new", "changed", "pages", "oldest_posted_utc", "newest_posted_utc", "overlap"]
MAX_PAGES = 8


SKILLS_CSV = ROOT / "seeds" / "skills.csv"
TAG = re.compile(r"<[^>]+>")


def load_skill_dict(path: Path = SKILLS_CSV) -> tuple[list[tuple[str, str, "re.Pattern"]], str]:
    """기술 사전과 그 판 번호(내용 해시 앞 8자). scope 가 title 이면 제목에서만 찾습니다(직무 이름)."""
    raw = path.read_bytes()
    with path.open(encoding="utf-8", newline="") as f:
        rules = [(r["skill"], r["scope"], re.compile(r["pattern"], re.I)) for r in csv.DictReader(f)]
    return rules, hashlib.sha256(raw).hexdigest()[:8]


def find_skills(title: str, body: str, rules) -> str:
    """제목(+본문)에서 사전에 있는 기술 이름을 찾아 '|' 로 이은 문자열. 본문은 HTML 태그를 떼고 봅니다."""
    text = title + " \n " + TAG.sub(" ", body or "")
    hit = [name for name, scope, pat in rules if pat.search(title if scope == "title" else text)]
    return "|".join(sorted(hit))


def fix_mojibake(s: str) -> str:
    """UTF-8 글자가 Latin-1 로 한 번 더 풀린 문자열을 되돌립니다 (예: 'â\\x80\\x94' → '—').

    Remote OK 제목에서 실제로 나온 문제입니다. 되돌릴 수 없으면(이미 정상인 문자열) 그대로 둡니다.
    """
    if not s or not any(c in s for c in "âÃÂ"):
        return s
    try:
        fixed = s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s
    return fixed


def clean(s) -> str:
    return " ".join(fix_mojibake(str(s or "")).split())[:200]


def iso(epoch) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_remoteok(x: dict, rules=()) -> dict | None:
    """Remote OK 한 건 → 공통 형식. 태그는 쓰지 않습니다(직무와 무관한 자동 태그가 많음 — README 참고)."""
    if not x.get("id") or not x.get("position"):
        return None
    lo, hi = int(x.get("salary_min") or 0), int(x.get("salary_max") or 0)
    return {"source": "remoteok", "job_id": str(x["id"]), "title": clean(x["position"]), "company": clean(x.get("company")),
            "location": clean(x.get("location")), "remote": "true", "posted_at_utc": iso(x["epoch"]),
            "salary_min": lo or "", "salary_max": hi or "", "url": str(x.get("url") or "").replace("remoteOK.com", "remoteok.com"),
            "skills": find_skills(clean(x["position"]), str(x.get("description") or ""), rules)}


def norm_arbeitnow(x: dict, rules=()) -> dict | None:
    if not x.get("slug") or not x.get("title"):
        return None
    return {"source": "arbeitnow", "job_id": str(x["slug"])[:160], "title": clean(x["title"]), "company": clean(x.get("company_name")),
            "location": clean(x.get("location")), "remote": "true" if x.get("remote") else "false", "posted_at_utc": iso(x["created_at"]),
            "salary_min": "", "salary_max": "", "url": str(x.get("url") or ""),
            "skills": find_skills(clean(x["title"]), str(x.get("description") or ""), rules)}


def content_hash(r: dict) -> str:
    key = "|".join(str(r.get(k, "")) for k in ("title", "company", "location", "remote", "salary_min", "salary_max"))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def http_json(url: str, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_remoteok(get=http_json, rules=()) -> tuple[list[dict], int]:
    data = get("https://remoteok.com/api")
    rows = [n for n in (norm_remoteok(x, rules) for x in data if isinstance(x, dict) and "id" in x) if n]
    return rows, 1


def fetch_arbeitnow(known: set[str], get=http_json, pause=1.0, max_pages=MAX_PAGES, first_run_pages=3, rules=()) -> tuple[list[dict], int]:
    """최신순 쪽을 넘기다가, 이미 아는 공고가 한 건이라도 나온 쪽에서 멈춥니다 (그 뒤는 지난번에 받은 구간).

    처음 실행(아는 공고 없음)은 first_run_pages 쪽만 받습니다.
    """
    rows, page = [], 0
    limit = max_pages if known else first_run_pages
    while page < limit:
        page += 1
        data = get(f"https://www.arbeitnow.com/api/job-board-api?page={page}").get("data") or []
        got = [n for n in (norm_arbeitnow(x, rules) for x in data) if n]
        rows += got
        if not got or any(r["job_id"] in known for r in got):
            break
        if page < limit:
            time.sleep(pause)
    return rows, page


def load(path: Path = JOBS) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {(r["source"], r["job_id"]): r for r in csv.DictReader(f)}


def merge(existing: dict, fetched: list[dict], today: str, dict_version: str = "") -> dict:
    """받은 공고를 기존 표에 합칩니다 (같은 날 여러 번 돌려도 결과가 같음).

    - 처음 보는 공고: first_seen = last_seen = 오늘
    - 이미 있는 공고: last_seen 만 오늘로. 내용(제목·급여 등)이 바뀌었으면 값을 바꾸고 changed_on 에 오늘을 적음
    한 번에 같은 공고가 두 번 들어오면(쪽 경계) 뒤의 것으로 한 건만 남깁니다.
    """
    stats = {"new": 0, "changed": 0}
    seen_now = {}
    for r in fetched:
        seen_now[(r["source"], r["job_id"])] = r
    for key, r in seen_now.items():
        h = content_hash(r)
        old = existing.get(key)
        if old is None:
            existing[key] = {**r, "skills_dict": dict_version, "content_hash": h, "first_seen": today, "last_seen": today, "changed_on": ""}
            stats["new"] += 1
        else:
            changed_on = old.get("changed_on", "")
            if old.get("content_hash") != h:
                if changed_on != today or old.get("first_seen") != today:
                    stats["changed"] += 1
                changed_on = today
            existing[key] = {**old, **r, "skills_dict": dict_version, "content_hash": h, "first_seen": old["first_seen"],
                             "last_seen": max(old["last_seen"], today), "changed_on": changed_on}
    return stats


def save(rows: dict, path: Path = JOBS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for key in sorted(rows, key=lambda k: (rows[k]["posted_at_utc"], k)):
            w.writerow(rows[key])
    os.replace(tmp, path)


def log_fetch(entries: list[dict], path: Path = FETCH_LOG) -> None:
    """하루 × 출처 한 줄. 같은 날 다시 돌리면 그 날 줄에 합칩니다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    prev = {(r["run_date"], r["source"]): r for r in rows}
    merged = []
    for e in entries:
        e = {k: e.get(k, "") for k in LOG_FIELDS}
        old = prev.pop((e["run_date"], e["source"]), None)
        if old and not str(e["overlap"]).startswith("error"):
            # 같은 날 다시 돌린 경우: 그날 처음 실행의 판정(first_run·yes·no)을 지키고, 새로 들어온 수는 더합니다
            num = lambda v: int(v or 0)
            e.update(fetched=max(num(old["fetched"]), num(e["fetched"])), new=num(old["new"]) + num(e["new"]),
                     changed=num(old["changed"]) + num(e["changed"]), pages=max(num(old["pages"]), num(e["pages"])),
                     oldest_posted_utc=min(x for x in (old["oldest_posted_utc"], e["oldest_posted_utc"]) if x),
                     newest_posted_utc=max(old["newest_posted_utc"], e["newest_posted_utc"]),
                     overlap=old["overlap"] if not str(old["overlap"]).startswith("error") else e["overlap"])
        elif old:
            e = old      # 다시 돌린 쪽이 실패했으면 앞의 성공 기록을 지키기
        merged.append(e)
    rows = list(prev.values()) + merged
    rows.sort(key=lambda r: (r["run_date"], r["source"]))
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def collect(today: str | None = None, jobs_path: Path = JOBS, log_path: Path = FETCH_LOG, get=http_json, pause=1.0) -> list[dict]:
    """두 출처를 받아 합치고 수집 기록을 남깁니다. 한 출처가 실패해도 다른 출처는 계속합니다."""
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing = load(jobs_path)
    rules, version = load_skill_dict()
    out = []
    for source, fetch in (("remoteok", lambda known: fetch_remoteok(get, rules)),
                          ("arbeitnow", lambda known: fetch_arbeitnow(known, get, pause, rules=rules))):
        known = {jid for (s, jid) in existing if s == source}
        try:
            rows, pages = fetch(known)
        except Exception as e:  # 네트워크·형식 오류: 기록만 남기고 다음 출처로
            out.append({"run_date": today, "source": source, "fetched": 0, "new": 0, "changed": 0, "pages": 0,
                        "oldest_posted_utc": "", "newest_posted_utc": "", "overlap": f"error:{type(e).__name__}"})
            continue
        overlap = any(r["job_id"] in known for r in rows)
        stats = merge(existing, rows, today, version)
        posted = sorted(r["posted_at_utc"] for r in rows)
        out.append({"run_date": today, "source": source, "fetched": len(rows), **stats, "pages": pages,
                    "oldest_posted_utc": posted[0] if posted else "", "newest_posted_utc": posted[-1] if posted else "",
                    "overlap": "first_run" if not known else ("yes" if overlap else "no")})
    save(existing, jobs_path)
    log_fetch(out, log_path)
    return out
