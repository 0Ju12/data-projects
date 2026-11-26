"""칸을 시군 단위로 나누기.

칸이 붙은 도로의 행정구역(HOT 내보내기의 adm1_name·adm2_name)을 칸의 행정구역으로 쓴다.
HOT 의 행정구역 표시는 경계가 오래됐거나 틀린 곳이 있어 아래에서 바로잡는다 (2026-11 파일 기준 확인):
- 울진군이 강원(Gangwon)으로 표시됨 → 경북
- 2023년 대구로 편입된 군위군, 대구 달성군·수성구가 경북으로 표시됨 → 경북에서 뺌
- 경북 안의 'Buk-gu' 는 포항시 북구 → 포항시
경계 근처 칸은 붙은 도로가 이웃 시군 것이면 그쪽으로 들어갈 수 있다 (칸 1 km 수준의 오차).
"""

from __future__ import annotations

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
FIXES = {("Gangwon", "Uljin-gun"): "울진군", ("North Gyeongsang", "Buk-gu"): "포항시"}


def gyeongbuk_sigun(adm1: str, adm2: str) -> str | None:
    """경북 시군 한글 이름, 경북이 아니면 None."""
    if (adm1, adm2) in FIXES:
        return FIXES[(adm1, adm2)]
    if adm1 == "North Gyeongsang":
        return GYEONGBUK.get(adm2)  # 달성군·군위군·수성구·창녕군 등은 None
    return None


def node_regions(compact: dict) -> dict[int, str | None]:
    """노드 → 경북 시군 (처음 본 도로 기준)."""
    out: dict[int, str | None] = {}
    for way in compact["ways"]:
        if len(way) < 5:
            continue
        sigun = gyeongbuk_sigun(*way[4])
        for i in way[3]:
            out.setdefault(i, sigun)
    return out
