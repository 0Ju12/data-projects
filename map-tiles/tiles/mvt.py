"""Mapbox Vector Tile 2.1 인코더 (점·다각형). protobuf 를 직접 쓴다.

명세: https://github.com/mapbox/vector-tile-spec/tree/master/2.1
- 좌표는 타일 안 정수(0..extent), 명령은 (id | count<<3), 인자는 이전 점과의 차이를 zigzag 로
- 다각형 바깥 고리는 타일 좌표(y 아래로)에서 넓이가 양수(시계 방향)
"""
from __future__ import annotations

import struct

POINT, LINESTRING, POLYGON = 1, 2, 3


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def zigzag(n: int) -> int:
    return (n << 1) ^ (n >> 63)


def _key(field: int, wire: int) -> bytes:
    return varint((field << 3) | wire)


def _bytes(field: int, data: bytes) -> bytes:
    return _key(field, 2) + varint(len(data)) + data


def _packed(field: int, nums: list[int]) -> bytes:
    return _bytes(field, b"".join(varint(n) for n in nums))


def _value(v) -> bytes:
    if isinstance(v, bool):
        return _key(7, 0) + varint(int(v))
    if isinstance(v, int):
        return _key(6, 0) + varint(zigzag(v)) if v < 0 else _key(5, 0) + varint(v)
    if isinstance(v, float):
        return _key(3, 1) + struct.pack("<d", v)
    return _bytes(1, str(v).encode("utf-8"))


def ring_area(ring: list[tuple[int, int]]) -> float:
    """측량사 공식 넓이 (타일 좌표). 양수 = MVT 바깥 고리."""
    return sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring))) / 2


def encode_geometry(gtype: int, parts: list[list[tuple[int, int]]]) -> list[int]:
    """점: parts = [[(x,y), …]] (점 여러 개는 MoveTo 하나에), 다각형: parts = 고리 목록 (닫는 점 없이)."""
    cmds: list[int] = []
    cx = cy = 0
    if gtype == POINT:
        pts = parts[0]
        cmds.append(1 | (len(pts) << 3))
        for x, y in pts:
            cmds += [zigzag(x - cx), zigzag(y - cy)]
            cx, cy = x, y
        return cmds
    for ring in parts:
        if gtype == POLYGON and len(ring) < 3:
            continue
        x, y = ring[0]
        cmds += [1 | (1 << 3), zigzag(x - cx), zigzag(y - cy)]
        cx, cy = x, y
        cmds.append(2 | ((len(ring) - 1) << 3))
        for x, y in ring[1:]:
            cmds += [zigzag(x - cx), zigzag(y - cy)]
            cx, cy = x, y
        if gtype == POLYGON:
            cmds.append(7 | (1 << 3))
    return cmds


class Layer:
    def __init__(self, name: str, extent: int = 4096):
        self.name, self.extent = name, extent
        self.keys: dict[str, int] = {}
        self.values: dict[tuple, int] = {}
        self.features: list[bytes] = []

    def _tags(self, props: dict) -> list[int]:
        tags = []
        for k, v in props.items():
            if v is None:
                continue
            ki = self.keys.setdefault(k, len(self.keys))
            vk = (type(v).__name__, v)
            vi = self.values.setdefault(vk, len(self.values))
            tags += [ki, vi]
        return tags

    def add(self, gtype: int, parts: list[list[tuple[int, int]]], props: dict, fid: int | None = None) -> None:
        geom = encode_geometry(gtype, parts)
        if not geom:
            return
        body = b""
        if fid is not None:
            body += _key(1, 0) + varint(fid)
        tags = self._tags(props)
        if tags:
            body += _packed(2, tags)
        body += _key(3, 0) + varint(gtype) + _packed(4, geom)
        self.features.append(body)

    def encode(self) -> bytes:
        out = _key(15, 0) + varint(2) + _bytes(1, self.name.encode("utf-8"))
        out += b"".join(_bytes(2, f) for f in self.features)
        out += b"".join(_bytes(3, k.encode("utf-8")) for k in self.keys)
        out += b"".join(_bytes(4, _value(v)) for (_, v) in self.values)
        out += _key(5, 0) + varint(self.extent)
        return out


def encode_tile(layers: list[Layer]) -> bytes:
    return b"".join(_bytes(3, l.encode()) for l in layers if l.features)
