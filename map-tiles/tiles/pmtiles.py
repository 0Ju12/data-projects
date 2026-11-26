"""PMTiles v3 쓰기 (한 파일 안에 모든 타일 + 위치 목록, HTTP 범위 요청으로 필요한 타일만 읽음).

명세: https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md
- 타일 번호: 줌 0..z-1 의 타일 수 + 힐베르트 곡선 위치
- 같은 내용의 타일(바다·빈 칸)은 한 번만 저장하고, 이어지는 번호는 run_length 로 묶음
- 머리글(127 B) + 루트 목록이 첫 16 KiB 안에 들어가야 함 → 넘치면 잎(leaf) 목록으로 나눔
"""

from __future__ import annotations

import gzip
import hashlib
import json
import struct
from dataclasses import dataclass

from .mvt import varint

HEADER_LEN = 127
ROOT_MAX = 16384 - HEADER_LEN
NONE, GZIP = 1, 2
MVT = 1


def zxy_to_tileid(z: int, x: int, y: int) -> int:
    if z > 31 or x >= 1 << z or y >= 1 << z:
        raise ValueError(f"타일 범위 밖: {z}/{x}/{y}")
    acc = ((1 << (2 * z)) - 1) // 3
    for a in range(z - 1, -1, -1):
        s = 1 << a
        rx = 1 if x & s else 0
        ry = 1 if y & s else 0
        acc += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
    return acc


@dataclass
class Entry:
    tile_id: int
    offset: int
    length: int
    run_length: int


def serialize_directory(entries: list[Entry]) -> bytes:
    out = bytearray(varint(len(entries)))
    last = 0
    for e in entries:
        out += varint(e.tile_id - last)
        last = e.tile_id
    for e in entries:
        out += varint(e.run_length)
    for e in entries:
        out += varint(e.length)
    for i, e in enumerate(entries):
        if i > 0 and e.offset == entries[i - 1].offset + entries[i - 1].length:
            out += varint(0)
        else:
            out += varint(e.offset + 1)
    return gzip.compress(bytes(out), mtime=0)


def _directories(entries: list[Entry]) -> tuple[bytes, bytes]:
    root = serialize_directory(entries)
    if len(root) <= ROOT_MAX:
        return root, b""
    leaf_size = 4096
    while True:
        leaves, root_entries, off = bytearray(), [], 0
        for i in range(0, len(entries), leaf_size):
            chunk = entries[i : i + leaf_size]
            data = serialize_directory(chunk)
            root_entries.append(Entry(chunk[0].tile_id, off, len(data), 0))  # run_length 0 = 잎 목록을 가리킴
            leaves += data
            off += len(data)
        root = serialize_directory(root_entries)
        if len(root) <= ROOT_MAX:
            return root, bytes(leaves)
        leaf_size *= 2


def write(
    path,
    tiles: dict[tuple[int, int, int], bytes],
    metadata: dict,
    bounds: tuple[float, float, float, float],
    center: tuple[float, float, int],
    tile_compression: int = GZIP,
) -> dict:
    """tiles: (z, x, y) → MVT 바이트 (압축 전). bounds = (서, 남, 동, 북). 통계를 돌려준다."""
    items = sorted((zxy_to_tileid(z, x, y), z, data) for (z, x, y), data in tiles.items())
    blob, entries, seen = bytearray(), [], {}
    for tid, _, data in items:
        body = gzip.compress(data, mtime=0) if tile_compression == GZIP else data
        h = hashlib.sha1(body).digest()
        if h in seen:
            off, ln = seen[h]
            last = entries[-1] if entries else None
            if last and last.offset == off and last.tile_id + last.run_length == tid:
                last.run_length += 1
                continue
            entries.append(Entry(tid, off, ln, 1))
            continue
        seen[h] = (len(blob), len(body))
        entries.append(Entry(tid, len(blob), len(body), 1))
        blob += body
    root, leaves = _directories(entries)
    meta = gzip.compress(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0)
    zooms = [z for _, z, _ in items]
    root_off = HEADER_LEN
    meta_off = root_off + len(root)
    leaf_off = meta_off + len(meta)
    data_off = leaf_off + len(leaves)
    header = (
        b"PMTiles"
        + bytes([3])
        + struct.pack(
            "<QQQQQQQQQQQ",
            root_off,
            len(root),
            meta_off,
            len(meta),
            leaf_off,
            len(leaves),
            data_off,
            len(blob),
            len(items),
            len(entries),
            len(seen),
        )
    )
    w, s, e, n = bounds
    header += bytes([1, GZIP, tile_compression, MVT, min(zooms), max(zooms)])
    header += struct.pack("<iiii", round(w * 1e7), round(s * 1e7), round(e * 1e7), round(n * 1e7))
    header += bytes([center[2]]) + struct.pack("<ii", round(center[0] * 1e7), round(center[1] * 1e7))
    assert len(header) == HEADER_LEN
    with open(path, "wb") as f:
        f.write(header + root + meta + leaves + blob)
    return {
        "tiles": len(items),
        "entries": len(entries),
        "unique": len(seen),
        "bytes": data_off + len(blob),
        "leaf_directories": bool(leaves),
        "minzoom": min(zooms),
        "maxzoom": max(zooms),
    }
