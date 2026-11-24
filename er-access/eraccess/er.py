"""응급의료기관 목록 읽기·받기.

받는 곳: 공공데이터포털 '국립중앙의료원_전국 응급의료기관 정보 조회 서비스' (data.go.kr/data/15000563)
- 인증키(serviceKey)가 쿼리 문자열로 들어가고, 해외 IP 에서는 연결이 끊긴다. 한국에서 `fetch-er` 를 한 번 돌려 CSV 로 저장한다.
- 응답 항목 이름은 명세서로 아직 확인하지 않았다. 그래서 받은 XML 항목을 이름 그대로 모두 CSV 에 저장하고,
  읽을 때 아래 별칭 목록으로 열을 찾는다. 처음 받은 뒤 별칭을 실제 이름에 맞게 정리할 것.
"""
from __future__ import annotations

import csv
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from .tables import pick, read_rows

NAME = ["기관명", "의료기관명", "병원명", "dutyName"]
LAT = ["위도", "병원위도", "wgs84Lat", "lat", "latitude"]
LON = ["경도", "병원경도", "wgs84Lon", "lon", "lng", "longitude"]
TIER = ["응급의료기관종별", "종별", "구분", "응급의료기관분류명", "dutyEmclsName"]

# 응급의료법상 종별. 순서 = 중증도 대응 수준 (높은 쪽이 앞)
TIERS = {
    "regional": ("권역응급의료센터",),
    "local_center": ("지역응급의료센터",),
    "local_institution": ("지역응급의료기관",),
}


def normalize_tier(text: str) -> str:
    t = (text or "").replace(" ", "")
    for key, words in TIERS.items():
        if any(w in t for w in words):
            return key
    return "other"


def load(path: Path) -> list[dict]:
    rows = read_rows(path)
    if not rows:
        return []
    cols = list(rows[0].keys())
    c_name, c_lat, c_lon, c_tier = pick(cols, NAME), pick(cols, LAT), pick(cols, LON), pick(cols, TIER)
    missing = [n for n, c in (("기관명", c_name), ("위도", c_lat), ("경도", c_lon)) if c is None]
    if missing:
        raise ValueError(f"{path}: 열을 찾지 못함 {missing} (있는 열: {cols})")
    out, seen = [], set()
    for r in rows:
        try:
            lat, lon = float(r[c_lat]), float(r[c_lon])
        except (TypeError, ValueError):
            continue                                    # 좌표 없는 행은 뺀다 (개수는 summary 에 남김)
        if not (33.0 <= lat <= 39.0 and 124.0 <= lon <= 132.0):
            continue
        key = (r[c_name].strip(), round(lat, 5), round(lon, 5))
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": key[0], "lat": lat, "lon": lon,
                    "tier": normalize_tier(r.get(c_tier, "") if c_tier else "")})
    return out


API = "https://apis.data.go.kr/B552657/ErmctInfoInqireService/getEgytListInfoInqire"


def fetch(service_key: str, out: Path, rows_per_page: int = 500) -> int:
    """응급의료기관 목록 전체를 받아 CSV 로 저장. 저장한 행 수를 돌려준다."""
    items, page = [], 1
    while True:
        q = urllib.parse.urlencode({"serviceKey": service_key, "pageNo": page, "numOfRows": rows_per_page})
        with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
            root = ET.fromstring(r.read())
        code = root.findtext(".//resultCode")
        if code not in (None, "00"):
            raise RuntimeError(f"API 오류 {code}: {root.findtext('.//resultMsg')}")
        batch = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
        items += batch
        total = int(root.findtext(".//totalCount") or 0)
        if not batch or len(items) >= total:
            break
        page += 1
    cols = sorted({k for it in items for k in it})
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(items)
    return len(items)
