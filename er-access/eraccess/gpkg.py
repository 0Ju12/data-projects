"""HOT 국가별 OSM 도로 내보내기(GeoPackage)를 그래프용 압축 형식으로 바꾼다.

받는 곳: HDX 'hotosm_kor_roads' (https://data.humdata.org/dataset/hotosm_kor_roads), ODbL.
Overpass 공용 서버가 이 실행 환경에서 막히거나 과부하(504)여서, 나라 전체 파일을 한 번 받아 쓴다.

GeoPackage 는 SQLite 파일이라 표준 라이브러리 sqlite3 로 읽는다. 도형은 'GP' 머리말 + WKB.
이 파일에는 OSM 노드 번호가 없다. OSM 에서 교차로는 같은 노드(= 같은 좌표)를 공유하므로,
좌표를 1e-7° 로 맞춘 값을 노드 번호로 쓰면 원래의 연결 관계가 그대로 살아난다.
(입체교차처럼 노드를 공유하지 않는 곳은 좌표도 다르므로 잘못 이어지지 않는다.)
"""
from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

from .osm import _direction

ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def node_key(lat: float, lon: float) -> int:
    """1e-7° 격자 좌표를 정수 하나로. 한국 범위에서 겹치지 않는다."""
    return round(lat * 1e7) * 10_000_000_000 + round(lon * 1e7)


def _wkb_lines(buf: bytes, off: int = 0) -> tuple[list[list[tuple[float, float]]], int]:
    """WKB LineString / MultiLineString → [[(경도, 위도), …], …]."""
    bo = "<" if buf[off] == 1 else ">"
    (gtype,) = struct.unpack_from(bo + "I", buf, off + 1)
    off += 5
    t = gtype & 0x0FFFFFFF                                  # EWKB 의 Z/M 깃발 비트 제거
    iso, base = t // 1000, t % 1000                         # ISO WKB: 1xxx=Z, 2xxx=M, 3xxx=ZM
    has_z = bool(gtype & 0x80000000) or iso in (1, 3)
    has_m = bool(gtype & 0x40000000) or iso in (2, 3)
    dims = 2 + has_z + has_m
    if base == 2:
        (n,) = struct.unpack_from(bo + "I", buf, off)
        off += 4
        pts = []
        for _ in range(n):
            x, y = struct.unpack_from(bo + "dd", buf, off)
            pts.append((x, y))
            off += 8 * dims
        return [pts], off
    if base == 3:
        # 닫힌 도로(회전교차로 등)가 다각형으로 내보내진 경우: 고리마다 선으로 본다
        (nr,) = struct.unpack_from(bo + "I", buf, off)
        off += 4
        rings = []
        for _ in range(nr):
            (n,) = struct.unpack_from(bo + "I", buf, off)
            off += 4
            ring = []
            for _ in range(n):
                ring.append(struct.unpack_from(bo + "dd", buf, off))
                off += 8 * dims
            rings.append(ring)
        return rings, off
    if base in (5, 6):                                      # MultiLineString, MultiPolygon
        (n,) = struct.unpack_from(bo + "I", buf, off)
        off += 4
        out = []
        for _ in range(n):
            lines, off = _wkb_lines(buf, off)
            out += lines
        return out, off
    if base in (1, 4):                                      # 점(드물게 도로 등급이 잘못 붙은 노드) — 도로망에 쓸모없음
        return [], off
    raise ValueError(f"지원하지 않는 도형 유형 {gtype}")


def parse_geometry(blob: bytes) -> list[list[tuple[float, float]]]:
    if blob[:2] != b"GP":
        raise ValueError("GeoPackage 도형이 아님")
    flags = blob[3]
    env = ENVELOPE_BYTES[(flags >> 1) & 0b111]
    if flags & 0b10000:                                     # 빈 도형
        return []
    return _wkb_lines(blob, 8 + env)[0]


def _layer(con: sqlite3.Connection) -> tuple[str, str]:
    row = con.execute("SELECT table_name, column_name FROM gpkg_geometry_columns LIMIT 1").fetchone()
    if row is None:
        raise ValueError("gpkg_geometry_columns 가 비어 있음")
    return row[0], row[1]


def read(path: Path, bbox: list[float], classes: list[str]) -> dict:
    """bbox 에 걸치는 도로 중 classes 등급(+ _link)만 압축 형식으로. 도로마다 [시도, 시군구] 영문 이름을 덧붙인다."""
    s, w, n, e = bbox
    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    table, geom = _layer(con)
    cols = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
    want = [c for c in ("highway", "oneway", "maxspeed", "junction", "adm1_name", "adm2_name") if c in cols]
    rtree = f"rtree_{table}_{geom}"
    has_rtree = con.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (rtree,)).fetchone() is not None
    allowed = set(classes) | {c + "_link" for c in classes}
    sel = ", ".join(f't."{c}"' for c in want)
    if has_rtree:                                           # 공간 색인으로 범위 안 것만
        q = (f'SELECT t."{geom}", {sel} FROM "{table}" t JOIN "{rtree}" r ON t.rowid = r.id '
             f'WHERE r.maxx >= ? AND r.minx <= ? AND r.maxy >= ? AND r.miny <= ?')
        rows = con.execute(q, (w, e, s, n))
    else:
        rows = con.execute(f'SELECT t."{geom}", {sel} FROM "{table}" t')
    nodes: dict[str, list[float]] = {}
    ways = []
    for row in rows:
        tags = {c: (v if v is not None else "") for c, v in zip(want, row[1:])}
        hw = str(tags.get("highway", ""))
        if hw not in allowed or row[0] is None:
            continue
        ms = str(tags.get("maxspeed", ""))
        maxspeed = int(ms.split()[0]) if ms.split() and ms.split()[0].isdigit() else None
        direction = _direction({k: str(v) for k, v in tags.items()})
        for line in parse_geometry(row[0]):
            if not any(s <= lat <= n and w <= lon <= e for lon, lat in line) and not has_rtree:
                continue
            ids = []
            for lon, lat in line:
                k = node_key(lat, lon)
                nodes[str(k)] = [round(lat, 7), round(lon, 7)]
                ids.append(k)
            ways.append([hw, direction, maxspeed, ids, [str(tags.get("adm1_name", "")), str(tags.get("adm2_name", ""))]])
    con.close()
    return {"nodes": nodes, "ways": ways}
