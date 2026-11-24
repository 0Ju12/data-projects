"""매일 받은 공고를 누적 목록(data/postings.json)에 합치고, 달력 화면용 docs/jobs.json 을 만듭니다.

- first_seen: 처음 본 날. 등록일을 주지 않는 출처(점핏)는 이 날을 등록일로 씀
- last_seen: 마지막으로 목록에 있던 날. 마감 전인데 목록에서 사라지면 조기 마감으로 보고 이틀 뒤 뺌
- 마감이 지난 공고는 달력에서 지난 날을 볼 수 있게 30일 동안 남김
"""
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "postings.json"
OUT = ROOT / "docs" / "jobs.json"
KEEP_PAST = 30      # 마감 지난 공고를 남기는 날 수
GONE_AFTER = 2      # 목록에서 사라진 뒤 빼기까지 기다리는 날 수


def load(path=STORE):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def merge(store, rows, today):
    """store(dict id→공고)에 오늘 받은 rows 를 합침. 새 공고 수와 바뀐 공고 수를 돌려줌"""
    new = changed = 0
    t = today.isoformat()
    for r in rows:
        old = store.get(r["id"])
        if old is None:
            store[r["id"]] = dict(r, first_seen=t, last_seen=t)
            new += 1
            continue
        keep = {k: old[k] for k in ("first_seen",) if k in old}
        if any(old.get(k) != r.get(k) for k in ("title", "end", "roles", "newbie", "loc")):
            changed += 1
        store[r["id"]] = dict(old, **r, **keep, last_seen=t)
    return new, changed


def feed_of(pid):
    """공고 id → 수집 단위 (jumpit · kakao · gh:<공고판>) — 실패한 단위의 공고는 '사라짐'으로 보지 않으려고"""
    return pid.rsplit(":", 1)[0]


def prune(store, today, fetched_srcs):
    """오래된 공고 정리. fetched_srcs = 오늘 수집에 성공한 수집 단위(feed_of). 그 단위의 공고만 '사라짐'으로 판단(실패한 출처는 그대로 둠)"""
    drop = []
    for k, r in store.items():
        end = dt.date.fromisoformat(r["end"]) if r.get("end") else None
        seen = dt.date.fromisoformat(r["last_seen"])
        if end and (today - end).days > KEEP_PAST:
            drop.append(k)
        elif feed_of(k) in fetched_srcs and (today - seen).days > GONE_AFTER and (not end or end >= today):
            drop.append(k)
    for k in drop:
        del store[k]
    return len(drop)


def export(store, log, today, path=OUT):
    rows = sorted(store.values(), key=lambda r: (r.get("end") or "9999", r.get("co") or ""))
    for r in rows:
        r.setdefault("start", None)
        if not r.get("start"):
            r["start"] = r.get("first_seen")
        if r.get("end") is None and r.get("last_seen") != today.isoformat():
            r["gone"] = True   # 상시 공고가 오늘 목록에 없었음 (곧 정리됨)
    data = {"updated": today.isoformat(), "sources": log, "count": len(rows),
            "postings": [{k: r.get(k) for k in ("id", "src", "co", "title", "url", "roles", "stacks", "loc", "newbie", "start", "end", "tech", "first_seen")} for r in rows]}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return data


def save(store, path=STORE):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(dict(sorted(store.items())), ensure_ascii=False, indent=0), encoding="utf-8")
