"""공공데이터 CSV 읽기: 인코딩(CP949/UTF-8)과 기관마다 다른 열 이름을 흡수한다."""

from __future__ import annotations

import csv
import io
from pathlib import Path


def read_text(path: Path) -> str:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path}: UTF-8 도 CP949 도 아닌 인코딩")


def read_rows(path: Path) -> list[dict]:
    return list(csv.DictReader(io.StringIO(read_text(path))))


def pick(columns: list[str], aliases: list[str]) -> str | None:
    """열 이름 후보 중 처음 맞는 것. 공백·대소문자 차이는 무시."""
    norm = {c.replace(" ", "").lower(): c for c in columns}
    for a in aliases:
        hit = norm.get(a.replace(" ", "").lower())
        if hit:
            return hit
    return None
