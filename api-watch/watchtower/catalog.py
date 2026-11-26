"""Import the entire resource index; catalog links never become executable endpoints."""

import hashlib
import html
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SOURCES = [("korea", "한국 API·리소스", "README.md"), ("global", "글로벌 API", "GLOBAL_PUBLIC_APIS_KR.md")]
BASE = "https://raw.githubusercontent.com/yybmion/public-apis-4Kr/main/"


def cells(line):
    return [s.strip() for s in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def text(value):
    return html.unescape(re.sub(r"<[^>]+>", "", value).replace("`", "").replace("**", "").strip())


def parse_markdown(raw, source_id):
    category = "기타"
    auth_index = None
    items = []
    for line in raw.splitlines():
        if line.startswith(("## ", "### ")):
            category = text(line.lstrip("#").strip())
            auth_index = None
        if not line.startswith("|"):
            continue
        row = cells(line)
        if any(c in {"인증", "Auth", "Authentication"} for c in row):
            auth_index = next(i for i, c in enumerate(row) if c in {"인증", "Auth", "Authentication"})
        if len(row) < 2:
            continue
        match = re.search(r"\[([^\]]+)\]\((https?://[^\s]+?)\)", row[0])
        if not match:
            continue
        name, url = map(html.unescape, match.groups())
        if not name.strip() or not url.startswith(("https://", "http://")):
            continue
        auth = text(row[auth_index]) if auth_index is not None and auth_index < len(row) else "원문 확인"
        no_auth = auth.lower() in {"no", "none", "없음", "불필요", "✕", "❌", ""} and auth_index is not None
        items.append(
            {
                "id": hashlib.sha256(url.rstrip("/").encode()).hexdigest()[:16],
                "name": text(name),
                "url": url,
                "description": text(row[1]),
                "category": category,
                "auth": auth or "No",
                "auth_type": "none" if no_auth else "unknown" if auth == "원문 확인" else "required",
                "source": source_id,
            }
        )
    return items


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "0Ju12-API-Catalog/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read(2500001)
        if len(raw) > 2500000:
            raise ValueError("catalog size limit")
        return raw.decode("utf-8")


def sync(path, fetcher=download, force=False):
    path = Path(path)
    now = datetime.now(timezone.utc)
    day = now.astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()
    if path.exists() and not force:
        old = json.loads(path.read_text())
        if old.get("sync_date") == day:
            return old
    entries = []
    sources = []
    for sid, label, file in SOURCES:
        parsed = parse_markdown(fetcher(BASE + file), sid)
        if len(parsed) < 50:
            raise ValueError("unexpected catalog structure: " + file)
        entries.extend(parsed)
        sources.append(
            {
                "id": sid,
                "label": label,
                "url": "https://github.com/yybmion/public-apis-4Kr/blob/main/" + file,
                "count": len(parsed),
            }
        )
    unique = {}
    for row in entries:
        if row["id"] not in unique:
            unique[row["id"]] = row
    payload = {
        "schema_version": 1,
        "sync_date": day,
        "collected_at": now.isoformat(),
        "sources": sources,
        "entries": list(unique.values()),
        "count": len(unique),
        "license": "MIT",
        "attribution": "yybmion/public-apis-4Kr · 글로벌 목록 원본 public-apis/public-apis",
        "scope": "원문 Markdown 표의 API·리소스 링크 전체를 중복 URL 기준으로 통합합니다. 목록 수집과 실제 API 호출은 별도입니다. 인증·CORS 정보는 원문 기준이며 현재 이용 조건을 보증하지 않습니다.",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(path)
    return payload
