"""직접 쓴 MVT 인코더·PMTiles 작성기를 공식 파이썬 구현(mapbox-vector-tile, pmtiles)으로 거꾸로 읽어 확인."""

import gzip
import json
import random

import mapbox_vector_tile
from pmtiles.reader import MmapSource, Reader, all_tiles
from pmtiles.tile import zxy_to_tileid as ref_tileid
from tiles import build, mvt, pmtiles
from tiles.tiling import EXTENT, TileSet, world_xy


def decode(data):
    return mapbox_vector_tile.decode(data, default_options={"y_coord_down": True})


def test_varint_zigzag():
    assert mvt.varint(1) == b"\x01" and mvt.varint(300) == b"\xac\x02"
    assert [mvt.zigzag(n) for n in (0, -1, 1, -2, 2)] == [0, 1, 2, 3, 4]


def test_mvt_roundtrip_points_polygons_and_property_types():
    lay = mvt.Layer("t")
    lay.add(mvt.POINT, [[(10, 20)]], {"name": "가", "n": 3, "neg": -5, "x": 1.5, "ok": True, "skip": None}, fid=7)
    ring = [(0, 0), (100, 0), (100, 50), (0, 50)]
    assert mvt.ring_area(ring) > 0  # 타일 좌표(y 아래)에서 시계 방향 = 바깥 고리
    lay.add(mvt.POLYGON, [ring], {"name": "가"})
    d = decode(mvt.encode_tile([lay]))["t"]
    assert d["extent"] == 4096 and len(d["features"]) == 2
    p, g = d["features"]
    assert p["id"] == 7 and p["geometry"] == {"type": "Point", "coordinates": [10, 20]}
    assert p["properties"] == {"name": "가", "n": 3, "neg": -5, "x": 1.5, "ok": True}
    assert g["geometry"]["type"] == "Polygon" and g["geometry"]["coordinates"][0][:4] == [
        [0, 0],
        [100, 0],
        [100, 50],
        [0, 50],
    ]


def test_tileid_matches_reference():
    rng = random.Random(3)
    for _ in range(3000):
        z = rng.randint(0, 16)
        x = rng.randrange(1 << z)
        y = rng.randrange(1 << z)
        assert pmtiles.zxy_to_tileid(z, x, y) == ref_tileid(z, x, y)
    assert [pmtiles.zxy_to_tileid(1, x, y) for x, y in [(0, 0), (0, 1), (1, 1), (1, 0)]] == [1, 2, 3, 4]


def test_box_split_across_tiles_shares_edges():
    ts = TileSet()
    X, _ = world_xy(128.0, 36.0, 8)
    edge_lon = (X // EXTENT + 1) * EXTENT / ((1 << 8) * EXTENT) * 360 - 180  # 타일 경계 경도
    ts.add_box("c", 8, edge_lon - 0.02, 35.99, edge_lon + 0.02, 36.01, {"v": 1})
    tiles = sorted(k for k in ts.tiles)
    assert len(tiles) == 2 and tiles[0][1] + 1 == tiles[1][1]
    left = decode(ts.encode()[tiles[0]])["c"]["features"][0]["geometry"]["coordinates"][0]
    r = decode(ts.encode()[tiles[1]])["c"]["features"][0]["geometry"]["coordinates"][0]
    assert max(p[0] for p in left) > EXTENT and min(p[0] for p in r) < 0  # 경계 너머로 겹쳐 그려 틈이 없게


def test_point_near_edge_goes_into_neighbor_buffer():
    ts = TileSet()
    X, Y = world_xy(128.0, 36.0, 6)
    lon = ((X // EXTENT + 1) * EXTENT - 10) / ((1 << 6) * EXTENT) * 360 - 180  # 경계 10 단위 안쪽
    ts.add_point("p", 6, lon, 36.0, {})
    assert len(ts.tiles) == 2


def test_aggregate_snaps_rounded_centers_to_shared_edges():
    deg = 1 / 120
    cells = [
        [round((i + 0.5) * deg, 4), round((j + 0.5) * deg, 4), 10, 0, 5.0, None, 3.0]
        for i in range(4400, 4404)
        for j in range(15400, 15404)
    ]
    one = build._aggregate(cells, deg, 1)
    souths = sorted({r[0] for r in one})
    assert all(abs((b - a) - deg) < 1e-12 for a, b in zip(souths, souths[1:]))  # 반올림된 중심이어도 칸 경계가 딱 맞음
    four = build._aggregate(cells, deg, 4)
    assert len(four) == 1 and four[0][3] == 160 and four[0][4] == [5.0, None, 3.0]


def test_write_and_read_with_reference_reader(tmp_path):
    ts = TileSet()
    for z in range(0, 5):
        ts.add_point("p", z, 128.0, 36.0, {"z": z})
        ts.add_box("b", z, 120, 30, 135, 40, {"k": "같음"})
    enc = ts.encode()
    enc[(4, 0, 0)] = enc[(4, 1, 0)] = b""  # 같은 내용 → 한 번만 저장
    path = tmp_path / "t.pmtiles"
    st = pmtiles.write(path, enc, {"vector_layers": [{"id": "p", "fields": {}}]}, (120, 30, 135, 40), (128, 36, 3))
    assert st["unique"] < st["tiles"] == len(enc)
    with open(path, "rb") as f:
        r = Reader(MmapSource(f))
        h = r.header()
        assert (h["min_zoom"], h["max_zoom"], h["tile_type"].value, h["tile_compression"].value) == (0, 4, 1, 2)
        assert r.metadata()["vector_layers"][0]["id"] == "p"
        got = dict(all_tiles(r.get_bytes))
        assert len(got) == len(enc)
        z, x, y = next(k for k in enc if k[0] == 3 and enc[k])
        assert gzip.decompress(r.get(z, x, y)) == enc[(z, x, y)]


def test_leaf_directories_when_root_too_big(tmp_path, monkeypatch):
    monkeypatch.setattr(pmtiles, "ROOT_MAX", 40)  # 규칙적인 목록은 gzip 이 아주 잘 줄여서 작게 잡음
    tiles = {(10, x, y): bytes([x % 251, y % 251, 1]) for x in range(860, 900) for y in range(390, 420)}
    st = pmtiles.write(tmp_path / "l.pmtiles", tiles, {}, (120, 30, 135, 40), (128, 36, 3))
    assert st["leaf_directories"]
    with open(tmp_path / "l.pmtiles", "rb") as f:
        r = Reader(MmapSource(f))
        assert gzip.decompress(r.get(10, 880, 400)) == bytes([880 % 251, 400 % 251, 1])
        assert len(dict(all_tiles(r.get_bytes))) == len(tiles)


def test_build_from_repo_outputs(tmp_path):
    st = build.build(out=tmp_path)
    meta = json.loads((tmp_path / "layers.json").read_text(encoding="utf-8"))
    assert st["maxzoom"] == 11 and {layer["id"] for layer in meta["vector_layers"]} >= {
        "quakes",
        "fire_grid",
        "er_cells",
        "er_sites",
    }
    assert all(
        layer["maxzoom"] == 11 for layer in meta["vector_layers"]
    )  # 확대 시 레이어가 사라지지 않게 모두 최대 줌까지
    with open(tmp_path / "korea.pmtiles", "rb") as f:
        r = Reader(MmapSource(f))
        X, Y = world_xy(128.73, 36.57, 9)  # 안동
        layers = decode(gzip.decompress(r.get(9, int(X // EXTENT), int(Y // EXTENT))))
        assert "er_cells" in layers and "er_sites" in layers
        assert any(f["properties"].get("m_any") is not None for f in layers["er_cells"]["features"])
