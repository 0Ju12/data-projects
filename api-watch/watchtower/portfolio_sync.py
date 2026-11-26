"""Version-pinned import of public project/article metadata. Never opens sealed/private files."""

import concurrent.futures
import datetime
import json
import os
import re
import urllib.request
from pathlib import Path

import yaml

REPO = "0Ju12/0Ju12.github.io"
API = "https://api.github.com/repos/" + REPO
SITE = "https://0ju12.github.io"
SLUG = re.compile(r"^[A-Za-z0-9_-]{1,120}$")
LINKS = {
    "preparation": SITE + "/study/index.html",
    "study": SITE + "/study/index.html#/notes",
    "interview": SITE + "/study/index.html#/questions",
    "practice_log": SITE + "/study/index.html#/log",
    "ai_notes": SITE + "/posts/ai-trend.html",
    "monitor": "https://0ju12.github.io/data-projects/api-watch/",
}


def text(value, limit=2000):
    return str(value or "").strip()[:limit]


def public_url(value):
    from urllib.parse import urlsplit

    try:
        u = urlsplit(str(value))
        value = str(value).replace("https://0ju12.github.io/interview/", "https://0ju12.github.io/study/")
        return str(value) if u.scheme in ("https", "http") and u.netloc and not u.username and not u.password else ""
    except ValueError:
        return ""


def download(url):
    headers = {
        "User-Agent": "0Ju12-Portfolio-Sync/1.0",
        "Accept": "application/json" if url.startswith("https://api.github.com/") else "text/plain",
    }
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]

    # All requested URLs are constructed from the fixed repository and validated Git SHAs.
    class FixedHostRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, response_headers, newurl):
            from urllib.parse import urlsplit

            if urlsplit(newurl).netloc != urlsplit(req.full_url).netloc:
                raise ValueError("cross-host redirect")
            return super().redirect_request(req, fp, code, msg, response_headers, newurl)

    with urllib.request.build_opener(FixedHostRedirect()).open(
        urllib.request.Request(url, headers=headers), timeout=12
    ) as r:
        raw = r.read(1500001)
        if len(raw) > 1500000:
            raise ValueError("public metadata response limit")
        return raw.decode("utf-8")


def frontmatter(raw):
    m = re.match(r"^---\s*\n(.*?)\n---(?:\s*\n|$)", raw, re.S)
    return yaml.safe_load(m.group(1)) if m else {}


def build_metadata(profile, index, articles, source_sha, updated_at):
    if not isinstance(profile, dict) or not isinstance(index, list):
        raise ValueError("public project shape")
    base = {}
    for group in profile.get("activities", []):
        for item in group.get("projects") or []:
            key = item.get("id", "")
            if not SLUG.fullmatch(key):
                continue
            urls = [public_url(x.get("url")) for x in item.get("links", []) if isinstance(x, dict)]
            urls = [u for u in urls if u]
            # Existing project pages are the public source of record, not a new performance claim.
            base[key] = {
                "id": key,
                "title": text(item.get("title"), 180),
                "summary": text(item.get("summary")),
                "url": SITE + "/projects/" + key + ".html",
                "repository": next(
                    (u for u in urls if u.startswith("https://github.com/")), SITE + "/projects/" + key + ".html"
                ),
                "stack": [],
                "links": urls[:15],
                "activity_id": key,
            }
    grouped = {}
    for item in index:
        if isinstance(item, dict) and SLUG.fullmatch(str(item.get("id", ""))):
            grouped.setdefault(item.get("activity") or item["id"], []).append(item)
    projects = []
    used = set()
    for activity, items in grouped.items():
        for item in items:
            key = activity if len(items) == 1 and activity in base else item["id"]
            original = base.get(activity, {}) if len(items) == 1 else {}
            slug = item.get("post", "")
            url = SITE + "/posts/" + slug + ".html" if SLUG.fullmatch(str(slug)) else original.get("url", SITE + "/")
            urls = [public_url(x.get("url")) for x in item.get("links", []) if isinstance(x, dict)]
            urls = [u for u in urls if u]
            projects.append(
                {
                    "id": key,
                    "title": text(item.get("title"), 180),
                    "summary": text(item.get("oneliner") or original.get("summary")),
                    "url": url,
                    "repository": next(
                        (u for u in urls if u.startswith("https://github.com/")), original.get("repository", url)
                    ),
                    "stack": [text(v, 100) for v in item.get("stack", []) if isinstance(v, str)][:20],
                    "links": list(dict.fromkeys([url] + urls + original.get("links", [])))[:20],
                    "activity_id": activity,
                }
            )
            used.add(activity)
    projects.extend(v for k, v in base.items() if k not in used)
    notes = []
    for path, meta in articles:
        if not isinstance(meta, dict) or meta.get("series") != "ai-trend":
            continue
        slug = Path(path).stem
        if not SLUG.fullmatch(slug):
            continue
        episode = meta.get("episode")
        if not isinstance(episode, int) or isinstance(episode, bool) or not 1 <= episode <= 10000:
            continue
        date = str(meta.get("date") or "")
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            raise ValueError("article date") from None
        notes.append(
            {
                "id": slug,
                "title": text(meta.get("title"), 300),
                "summary": text(meta.get("summary")),
                "date": date,
                "episode": episode,
                "url": SITE + "/posts/" + slug + ".html",
                "label": "내 포트폴리오의 AI 기술 정리 · 공식 신규 발표와 구분",
            }
        )
    if not projects:
        raise ValueError("empty public projects")
    return {
        "schema_version": 1,
        "source_repository": REPO,
        "source_sha": source_sha,
        "source_updated_at": updated_at,
        "synced_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "links": LINKS,
        "projects": projects,
        "learning_notes": sorted(notes, key=lambda n: n["episode"], reverse=True),
        "scope": "공개 프로젝트 YAML과 공개 AI 글의 제목·요약만 가져옵니다. 기존 개인 기록과 실험 결과를 수정하지 않습니다.",
    }


def sync(path, fetcher=download, force=False):
    path = Path(path)
    commit = json.loads(fetcher(API + "/commits/main"))
    sha = commit.get("sha", "")
    tree_sha = commit.get("commit", {}).get("tree", {}).get("sha", "")
    if not re.fullmatch("[0-9a-f]{40}", sha) or not re.fullmatch("[0-9a-f]{40}", tree_sha):
        raise ValueError("source revision")
    if path.exists() and not force:
        try:
            old = json.loads(path.read_text())
        except (ValueError, OSError):
            old = {}
        if isinstance(old, dict) and old.get("schema_version") == 1 and old.get("source_sha") == sha:
            return old
    raw = "https://raw.githubusercontent.com/" + REPO + "/" + sha + "/"
    tree = json.loads(fetcher(API + "/git/trees/" + tree_sha + "?recursive=1"))
    if tree.get("truncated"):
        raise ValueError("incomplete source tree")
    paths = [
        x["path"]
        for x in tree.get("tree", [])
        if x.get("type") == "blob"
        and re.fullmatch(r"content/posts/[A-Za-z0-9_-]*ai-trend[A-Za-z0-9_-]*\.md", x.get("path", ""))
    ]
    if len(paths) > 100:
        raise ValueError("too many public notes")

    def article(path):
        return path, frontmatter(fetcher(raw + path))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        articles = list(pool.map(article, paths))
    data = build_metadata(
        yaml.safe_load(fetcher(raw + "data/portfolio.yaml")),
        yaml.safe_load(fetcher(raw + "data/projects_index.yaml")),
        articles,
        sha,
        commit.get("commit", {}).get("committer", {}).get("date"),
    )
    note_paths = {
        x["path"]
        for x in tree.get("tree", [])
        if x.get("type") == "blob" and re.fullmatch(r"docs/study/notes/[A-Za-z0-9_-]+\.html", x.get("path", ""))
    }
    highlights = [
        {"title": title, "url": SITE + "/study/notes/" + slug + ".html"}
        for slug, title in [
            ("js_basic_syntax_2", "JavaScript · Basic Syntax 02"),
            ("js_controlling_event", "JavaScript · Controlling Event"),
        ]
        if "docs/study/notes/" + slug + ".html" in note_paths
    ]
    data["study"] = {"note_count": len(note_paths), "url": LINKS["study"], "highlights": highlights}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)
    return data
