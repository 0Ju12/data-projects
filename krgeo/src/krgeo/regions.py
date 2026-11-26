"""한국 행정구역 이름 정리와 HOT 내보내기의 행정구역 표시 보정.

HOT 국가별 OSM 내보내기(HDX hotosm_kor_*)는 도로·시설마다 adm1_name(시도)·adm2_name(시군구)을 영문으로 붙인다.
2026-11 파일에서 확인한 오류를 바로잡는다:
- 울진군이 강원(Gangwon)으로 표시됨 → 경상북도
- 2023년 7월 대구로 편입된 군위군, 대구 달성군·수성구가 경상북도로 표시됨 → 대구광역시
- 경상북도 안의 'Buk-gu' 는 포항시 북구 → 포항시

    >>> sido_ko("North Gyeongsang")
    '경상북도'
    >>> fix_admin("Gangwon", "Uljin-gun")
    ('경상북도', '울진군')
"""

from __future__ import annotations

SIDO = {
    "Seoul": "서울특별시",
    "Busan": "부산광역시",
    "Daegu": "대구광역시",
    "Incheon": "인천광역시",
    "Gwangju": "광주광역시",
    "Daejeon": "대전광역시",
    "Ulsan": "울산광역시",
    "Sejong": "세종특별자치시",
    "Gyeonggi": "경기도",
    "Gangwon": "강원특별자치도",
    "North Chungcheong": "충청북도",
    "South Chungcheong": "충청남도",
    "North Jeolla": "전북특별자치도",
    "South Jeolla": "전라남도",
    "North Gyeongsang": "경상북도",
    "South Gyeongsang": "경상남도",
    "Jeju": "제주특별자치도",
}

GYEONGBUK = {
    "Pohang-si": "포항시",
    "Gyeongju-si": "경주시",
    "Gimcheon-si": "김천시",
    "Andong-si": "안동시",
    "Gumi-si": "구미시",
    "Yeongju-si": "영주시",
    "Yeongcheon-si": "영천시",
    "Sangju-si": "상주시",
    "Mungyeong-si": "문경시",
    "Gyeongsan-si": "경산시",
    "Uiseong-gun": "의성군",
    "Cheongsong-gun": "청송군",
    "Yeongyang-gun": "영양군",
    "Yeongdeok-gun": "영덕군",
    "Cheongdo-gun": "청도군",
    "Goryeong-gun": "고령군",
    "Seongju-gun": "성주군",
    "Chilgok-gun": "칠곡군",
    "Yecheon-gun": "예천군",
    "Bonghwa-gun": "봉화군",
    "Uljin-gun": "울진군",
    "Ulleung-gun": "울릉군",
}
DAEGU_FROM_GB = {"Gunwi-gun": "군위군", "Dalseong-gun": "달성군", "Suseong-gu": "수성구"}

# (HOT 시도, HOT 시군구) → (바른 시도 한글, 바른 시군구 한글)
FIXES = {
    ("Gangwon", "Uljin-gun"): ("경상북도", "울진군"),
    ("North Gyeongsang", "Buk-gu"): ("경상북도", "포항시"),
    **{("North Gyeongsang", k): ("대구광역시", v) for k, v in DAEGU_FROM_GB.items()},
}


def sido_ko(adm1: str) -> str | None:
    return SIDO.get(adm1)


def fix_admin(adm1: str, adm2: str) -> tuple[str | None, str | None]:
    """HOT 의 (시도, 시군구) 영문 표시 → 보정한 한글 (시도, 시군구). 경상북도 밖 시군구는 한글 이름표가 없어 영문 그대로."""
    if (adm1, adm2) in FIXES:
        return FIXES[(adm1, adm2)]
    sido = SIDO.get(adm1)
    if adm1 == "North Gyeongsang":
        return sido, GYEONGBUK.get(adm2, adm2 or None)
    return sido, adm2 or None


def gyeongbuk_sigun(adm1: str, adm2: str) -> str | None:
    """경상북도 시군 한글 이름, 경상북도가 아니면 None (er-access 의 집계 범위)."""
    sido, sigun = fix_admin(adm1, adm2)
    return sigun if sido == "경상북도" and sigun in GYEONGBUK.values() else None


def node_regions(compact: dict, fn=gyeongbuk_sigun) -> dict[int, str | None]:
    """hotosm.read_roads 결과에서 노드 → 행정구역 (처음 본 도로 기준). fn 으로 원하는 구분을 고른다."""
    out: dict[int, str | None] = {}
    for way in compact["ways"]:
        if len(way) < 5:
            continue
        r = fn(*way[4])
        for i in way[3]:
            out.setdefault(i, r)
    return out
