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
            continue  # 좌표 없는 행은 뺀다 (개수는 summary 에 남김)
        if not (33.0 <= lat <= 39.0 and 124.0 <= lon <= 132.0):
            continue
        key = (r[c_name].strip(), round(lat, 5), round(lon, 5))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {"name": key[0], "lat": lat, "lon": lon, "tier": normalize_tier(r.get(c_tier, "") if c_tier else "")}
        )
    return out


def from_osm(data: dict) -> list[dict]:
    """OSM 의 amenity=hospital + emergency=yes. 공식 목록이 없을 때 쓰는 **임시** 목록이다.
    한국 OSM 은 응급실 태그가 빠진 병원이 많고 종별 정보가 없어, 이 목록으로 낸 시간은 실제보다 길게 나온다."""
    out, seen = [], set()
    for el in data.get("elements", []):
        lat = el.get("lat", el.get("center", {}).get("lat"))
        lon = el.get("lon", el.get("center", {}).get("lon"))
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        name = tags.get("name:ko") or tags.get("name") or f"OSM {el['type']}/{el['id']}"
        key = (name, round(lat, 3), round(lon, 3))
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "lat": lat, "lon": lon, "tier": "other"})
    return out


def merge_provisional(osm_rows: list[dict], centers: list[dict], within_m: float = 300) -> list[dict]:
    """임시 목록 = 위키백과 권역센터(종별 있음) + OSM 응급실 태그. 같은 병원이 두 곳에 있으면(300 m 안) 권역센터 쪽을 남긴다."""
    from .geo import haversine_m

    out = list(centers)
    for r in osm_rows:
        if not any(haversine_m(r["lat"], r["lon"], c["lat"], c["lon"]) <= within_m for c in centers):
            out.append(r)
    return out


def save(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["기관명", "위도", "경도", "종별"])
        for r in rows:
            w.writerow([r["name"], f"{r['lat']:.6f}", f"{r['lon']:.6f}", TIERS.get(r["tier"], ("",))[0]])


BASE = "https://apis.data.go.kr/B552657/ErmctInfoInqireService"
API = f"{BASE}/getEgytListInfoInqire"  # 응급의료기관 목록
BEDS_API = f"{BASE}/getEmrrmRltmUsefulSckbdInfoInqire"  # 응급실 실시간 가용 병상


def parse_items(xml_bytes: bytes) -> tuple[list[dict], int]:
    """공공데이터포털 XML 응답 → (항목 목록, totalCount). 오류 코드는 예외로."""
    root = ET.fromstring(xml_bytes)
    code = root.findtext(".//resultCode")
    if code not in (None, "00"):
        raise RuntimeError(f"API 오류 {code}: {root.findtext('.//resultMsg')}")
    items = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
    return items, int(root.findtext(".//totalCount") or 0)


def _all_pages(url: str, params: dict, rows_per_page: int = 500, opener=urllib.request.urlopen) -> list[dict]:
    items, page = [], 1
    while True:
        q = urllib.parse.urlencode({**params, "pageNo": page, "numOfRows": rows_per_page})
        with opener(f"{url}?{q}", timeout=60) as r:
            batch, total = parse_items(r.read())
        items += batch
        if not batch or len(items) >= total:
            return items
        page += 1


def _write_csv(items: list[dict], out: Path, extra: dict | None = None, append: bool = False) -> int:
    rows = [{**(extra or {}), **it} for it in items]
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = sorted({k for r in rows for k in r})
    if append and out.exists():
        with open(out, encoding="utf-8") as f:
            old = list(csv.DictReader(f))
        cols = sorted(set(cols) | {k for r in old for k in r})
        rows = old + rows
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return len(items)


def fetch(service_key: str, out: Path, rows_per_page: int = 500, opener=urllib.request.urlopen) -> int:
    """응급의료기관 목록 전체를 받아 CSV 로 저장. 저장한 행 수를 돌려준다."""
    return _write_csv(_all_pages(API, {"serviceKey": service_key}, rows_per_page, opener), out)


def fetch_beds(
    service_key: str, out: Path, sido: str = "경상북도", when: str = "", opener=urllib.request.urlopen
) -> int:
    """응급실 실시간 가용 병상 한 번 찍기 → out 에 이어 붙임 (수집 시각 열 'collected_at' 추가).
    정기적으로 돌리면(예: 매시) 시간대·요일별 혼잡을 볼 수 있다. 응답 항목은 이름 그대로 모두 저장한다
    (명세서상 hvec = 응급실 가용 병상 수로 알려져 있으나 받은 뒤 확인할 것)."""
    items = _all_pages(BEDS_API, {"serviceKey": service_key, "STAGE1": sido}, 500, opener)
    return _write_csv(items, out, {"collected_at": when}, append=True)
