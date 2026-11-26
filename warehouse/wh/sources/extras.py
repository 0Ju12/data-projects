"""패키지 내려받기 수(PyPI · npm)와 자연재해 경보(GDACS) 수집 — 모두 키 없는 공개 API

- 내려받기 수: 기술 사전의 기술과 짝지은 패키지만(seeds/packages.csv). 어제까지의 값만 저장하고, 최근 10일은 다시 받아 바꿉니다
  (집계가 며칠 늦게 확정됨). pypistats 는 최근 180일만 주므로 그 전 기록은 처음 수집한 날부터 쌓입니다.
- 재해 경보: 태풍(TC)·홍수(FL)·화산(VO)·가뭄(DR). 지진은 따로 모으고 있고, 산불(WF)은 건수가 많아 뺐습니다.
  사건의 경보 등급과 종료일은 진행 중에 바뀌므로 최근 90일을 매일 다시 받아 최신 상태로 덮습니다 (등급 변화 이력은 dbt snapshot 이 쌓음).
"""

from __future__ import annotations

import csv
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from .jobs import clean, http_json
from .market import _load, _save

ROOT = Path(__file__).resolve().parent.parent.parent
PKG = ROOT / "data" / "pkg_downloads.csv"
PKG_SEED = ROOT / "seeds" / "packages.csv"
DIS = ROOT / "data" / "disasters.csv"
P_FIELDS = ["registry", "package", "day", "downloads"]
D_FIELDS = [
    "event_key",
    "event_type",
    "name",
    "country",
    "iso3",
    "alert_level",
    "alert_score",
    "severity",
    "severity_unit",
    "from_date",
    "to_date",
    "modified_at",
    "lon",
    "lat",
    "is_current",
]
PKG_OVERLAP = 10
DIS_WINDOW = 90
DIS_TYPES = "TC,FL,VO,DR"


def packages(path: Path = PKG_SEED) -> list[tuple[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return [(r["registry"], r["package"]) for r in csv.DictReader(f)]


def pypi_days(package: str, start: date, end: date, get=http_json) -> list[dict]:
    data = get(f"https://pypistats.org/api/packages/{quote(package)}/overall?mirrors=false").get("data") or []
    return [
        {"registry": "pypi", "package": package, "day": r["date"], "downloads": int(r["downloads"])}
        for r in data
        if start.isoformat() <= r["date"] <= end.isoformat()
    ]


def npm_days(package: str, start: date, end: date, get=http_json) -> list[dict]:
    data = (
        get(
            f"https://api.npmjs.org/downloads/range/{start.isoformat()}:{end.isoformat()}/{quote(package, safe='@')}"
        ).get("downloads")
        or []
    )
    return [
        {"registry": "npm", "package": package, "day": r["day"], "downloads": int(r["downloads"])}
        for r in data
        if start.isoformat() <= r["day"] <= end.isoformat()
    ]


def collect_packages(
    today: str | None = None,
    path: Path = PKG,
    seed: Path = PKG_SEED,
    get=http_json,
    pause=1.2,
    backfill_days: int = 365,
) -> dict:
    today_d = date.fromisoformat(today) if today else datetime.now(timezone.utc).date()
    end = today_d - timedelta(days=2)  # 어제 값도 아직 덜 찬 경우가 있어 이틀 전까지만
    rows = _load(path, lambda r: (r["registry"], r["package"], r["day"]))
    st = {"end": end.isoformat(), "new": 0, "changed": 0, "errors": []}
    for i, (registry, package) in enumerate(packages(seed)):
        have = [k[2] for k in rows if k[0] == registry and k[1] == package]
        start = (
            max(date.fromisoformat(max(have)) - timedelta(days=PKG_OVERLAP), end - timedelta(days=backfill_days))
            if have
            else end - timedelta(days=backfill_days)
        )
        try:
            got = (pypi_days if registry == "pypi" else npm_days)(package, start, end, get)
        except Exception as e:
            st["errors"].append(f"{registry}:{package}:{type(e).__name__}")
            continue
        for r in got:
            k = (r["registry"], r["package"], r["day"])
            if k not in rows:
                st["new"] += 1
            elif str(rows[k]["downloads"]) != str(r["downloads"]):
                st["changed"] += 1
            rows[k] = r
        if pause and i:
            time.sleep(pause if registry == "pypi" else pause / 4)
    _save(rows, path, P_FIELDS)
    st["total"] = len(rows)
    return st


def norm_event(f: dict) -> dict | None:
    p = f.get("properties") or {}
    if not p.get("eventid") or not p.get("eventtype"):
        return None
    xy = (f.get("geometry") or {}).get("coordinates") or ["", ""]
    sev = p.get("severitydata") or {}
    return {
        "event_key": f"{p['eventtype']}-{p['eventid']}",
        "event_type": p["eventtype"],
        "name": clean(p.get("name") or p.get("eventname")),
        "country": clean(p.get("country")),
        "iso3": clean(p.get("iso3")),
        "alert_level": clean(p.get("alertlevel")),
        "alert_score": p.get("alertscore", ""),
        "severity": sev.get("severity", ""),
        "severity_unit": clean(sev.get("severityunit")),
        "from_date": str(p.get("fromdate", ""))[:19],
        "to_date": str(p.get("todate", ""))[:19],
        "modified_at": str(p.get("datemodified", ""))[:19],
        "lon": xy[0] if isinstance(xy[0], (int, float)) else "",
        "lat": xy[1] if isinstance(xy[0], (int, float)) else "",
        "is_current": str(p.get("iscurrent", "")).lower(),
    }


def collect_disasters(
    today: str | None = None, path: Path = DIS, get=http_json, pause=0.5, window: int = DIS_WINDOW, max_pages: int = 15
) -> dict:
    today_d = date.fromisoformat(today) if today else datetime.now(timezone.utc).date()
    start = today_d - timedelta(days=window)
    rows = _load(path, lambda r: r["event_key"])
    st = {"fetched": 0, "new": 0, "level_changed": 0, "pages": 0, "errors": []}
    try:
        for page in range(1, max_pages + 1):
            data = get(
                "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
                f"?eventlist={DIS_TYPES}&fromdate={start.isoformat()}&todate={today_d.isoformat()}"
                f"&alertlevel=Green;Orange;Red&pagenumber={page}"
            )
            feats = (data or {}).get("features") or []
            st["pages"] = page
            for f in feats:
                e = norm_event(f)
                if not e:
                    continue
                st["fetched"] += 1
                old = rows.get(e["event_key"])
                if old is None:
                    st["new"] += 1
                elif old.get("alert_level") != e["alert_level"]:
                    st["level_changed"] += 1
                rows[e["event_key"]] = e
            if len(feats) < 100:
                break
            time.sleep(pause)
    except Exception as e:
        st["errors"].append(type(e).__name__)
    _save(rows, path, D_FIELDS)
    st["total"] = len(rows)
    return st
