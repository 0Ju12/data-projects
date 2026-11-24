"""교통사고 CSV 읽기.

받는 곳(공공데이터포털, 한국 IP 에서 로그인 후 내려받기):
- 도로교통공단 사망 교통사고 정보 (사고 한 건 = 한 줄, 위경도 또는 UTM-K 좌표)
- 전국교통사고다발지역표준데이터 (data.go.kr/data/15029185) — 공식 다발 지역, 결과 대조용

연도·기관마다 열 이름이 조금씩 달라 별칭으로 찾는다. 위경도 열이 없으면 UTM-K(EPSG:5179) 열을 바꿔 쓴다.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .utmk import to_utmk, to_wgs84

WHEN = ["발생년월일시", "발생일시", "사고일시", "occrrnc_dt"]
LAT = ["위도", "la_crd", "lat", "latitude"]
LON = ["경도", "lo_crd", "lon", "lng", "longitude"]
UX = ["발생위치X(UTMK)", "발생위치X_UTMK", "X좌표", "utmk_x"]
UY = ["발생위치Y(UTMK)", "발생위치Y_UTMK", "Y좌표", "utmk_y"]
DEATHS = ["사망자수", "dth_dnv_cnt"]
KIND = ["사고유형_대분류", "사고유형대분류", "사고유형", "acc_ty_lclas_nm"]
ROAD = ["도로형태_대분류", "도로형태", "road_frm_lclas_nm"]


def read_rows(path: Path) -> list[dict]:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return list(csv.DictReader(io.StringIO(raw.decode(enc))))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path}: UTF-8 도 CP949 도 아닌 인코딩")


def pick(columns: list[str], aliases: list[str]) -> str | None:
    norm = {c.replace(" ", "").lower(): c for c in columns}
    for a in aliases:
        hit = norm.get(a.replace(" ", "").lower())
        if hit:
            return hit
    return None


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def load(path: Path) -> tuple[list[dict], dict]:
    """사고 목록과 읽기 통계(빠진 행 수 등)."""
    rows = read_rows(path)
    stats = {"file": Path(path).name, "rows": len(rows), "kept": 0, "no_coord": 0, "outside_korea": 0}
    if not rows:
        return [], stats
    cols = list(rows[0].keys())
    c = {k: pick(cols, al) for k, al in
         {"when": WHEN, "lat": LAT, "lon": LON, "ux": UX, "uy": UY, "deaths": DEATHS, "kind": KIND, "road": ROAD}.items()}
    use_wgs = c["lat"] and c["lon"]
    if not use_wgs and not (c["ux"] and c["uy"]):
        raise ValueError(f"{path}: 좌표 열(위도·경도 또는 UTM-K X·Y)을 찾지 못함 (있는 열: {cols})")
    out = []
    for r in rows:
        if use_wgs:
            lat, lon = _num(r[c["lat"]]), _num(r[c["lon"]])
            if lat is None or lon is None:
                stats["no_coord"] += 1
                continue
            x, y = to_utmk(lat, lon) if 30 < lat < 45 else (None, None)
        else:
            x, y = _num(r[c["ux"]]), _num(r[c["uy"]])
            if x is None or y is None:
                stats["no_coord"] += 1
                continue
            lat, lon = to_wgs84(x, y)
        if x is None or not (33.0 <= lat <= 38.7 and 124.5 <= lon <= 132.0):
            stats["outside_korea"] += 1
            continue
        out.append({
            "when": (r.get(c["when"]) or "").strip() if c["when"] else "",
            "lat": lat, "lon": lon, "x": x, "y": y,
            "deaths": _num(r.get(c["deaths"])) if c["deaths"] else None,
            "kind": (r.get(c["kind"]) or "").strip() if c["kind"] else "",
            "road": (r.get(c["road"]) or "").strip() if c["road"] else "",
        })
    stats["kept"] = len(out)
    return out, stats
