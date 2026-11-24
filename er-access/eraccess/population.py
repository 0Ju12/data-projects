"""WorldPop 1 km 격자 인구 (2020, UN 보정 전 추정치) 읽기.

파일: kor_ppp_2020_1km_ASCII_XYZ.zip — 안에 X(경도),Y(위도),Z(인구) CSV 하나. 칸 중심 좌표, 해상도 30초(약 0.0083°).
CC BY 4.0, 출처 표기: "WorldPop (www.worldpop.org)".
"""
from __future__ import annotations

import csv
import io
import urllib.request
import zipfile
from pathlib import Path

URL = "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2020/KOR/kor_ppp_2020_1km_ASCII_XYZ.zip"


def download(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        req = urllib.request.Request(URL, headers={"User-Agent": "data-projects/er-access"})
        with urllib.request.urlopen(req, timeout=300) as r:
            dest.write_bytes(r.read())
    return dest


def _lines(path: Path):
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            with z.open(name) as f:
                yield from io.TextIOWrapper(f, encoding="utf-8")
    else:
        with open(path, encoding="utf-8") as f:
            yield from f


def load(path: Path, bbox: list[float], min_pop: float = 0.0) -> list[dict]:
    """bbox = [남, 서, 북, 동] 안의 칸만. 인구가 min_pop 이하인 칸(바다·산지 빈 칸)은 뺀다."""
    s, w, n, e = bbox
    out = []
    for r in csv.DictReader(_lines(Path(path))):
        lon, lat, pop = float(r["X"]), float(r["Y"]), float(r["Z"])
        if s <= lat <= n and w <= lon <= e and pop > min_pop:
            out.append({"lat": lat, "lon": lon, "pop": pop})
    return out
