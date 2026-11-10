"""USGS FDSN Event API 수집.

- 한 번에 받을 수 있는 최대 건수(20,000)를 넘지 않도록 기간을 나눠 요청합니다.
- 네트워크 오류·5xx 는 지수 백오프로 최대 4번 재시도하고, 그래도 실패하면 예외를 그대로 올립니다
  (조용히 빈 결과를 저장하지 않음 — 빈 결과와 실패를 구분하기 위해).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://earthquake.usgs.gov/fdsnws/event/1/"
MAX_PER_QUERY = 20000
UA = "geo-data-pipeline/1.0 (portfolio project)"


def _get(url: str, retries: int = 4, opener=urllib.request.urlopen) -> dict:
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with opener(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 204:          # 조건에 맞는 이벤트 없음
                return {"type": "FeatureCollection", "features": []}
            if e.code < 500 or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")


def query_params(region: dict, start: datetime, end: datetime) -> dict:
    return {
        "format": "geojson", "orderby": "time-asc",
        "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"), "endtime": end.strftime("%Y-%m-%dT%H:%M:%S"),
        "minlatitude": region["bbox"][0], "maxlatitude": region["bbox"][1],
        "minlongitude": region["bbox"][2], "maxlongitude": region["bbox"][3],
        "minmagnitude": region["min_mag"],
    }


def count(region: dict, start: datetime, end: datetime, opener=urllib.request.urlopen) -> int:
    p = query_params(region, start, end)
    p.pop("orderby")
    return int(_get(BASE + "count?" + urllib.parse.urlencode(p), opener=opener)["count"])


def fetch(region: dict, start: datetime, end: datetime, opener=urllib.request.urlopen) -> list[dict]:
    """[start, end) 구간의 이벤트(GeoJSON feature) 목록. 건수가 많으면 구간을 반으로 나눠 다시 요청."""
    n = count(region, start, end, opener=opener)
    if n == 0:
        return []
    if n > MAX_PER_QUERY * 0.9 and (end - start) > timedelta(days=1):
        mid = start + (end - start) / 2
        return fetch(region, start, mid, opener) + fetch(region, mid, end, opener)
    data = _get(BASE + "query?" + urllib.parse.urlencode(query_params(region, start, end)), opener=opener)
    return data.get("features", [])


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
