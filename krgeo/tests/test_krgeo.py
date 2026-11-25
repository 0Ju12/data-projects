import json
import sqlite3
import struct

import numpy as np
import pytest

from krgeo import access, hotosm, hotspot, regions
from krgeo.geo import PointIndex, haversine_m
from krgeo.graph import RoadGraph, multi_source_dijkstra
from krgeo.utmk import to_utmk, to_wgs84

LON0 = 129.00


def node(i, lon, lat=36.0):
    return {"type": "node", "id": i, "lat": lat, "lon": lon}


def _gp_line(coords, ewkb_z=False):
    gtype = 2 | (0x80000000 if ewkb_z else 0)
    body = struct.pack("<BII", 1, gtype, len(coords))
    for x, y in coords:
        body += struct.pack("<dd", x, y) + (struct.pack("<d", 0.0) if ewkb_z else b"")
    return b"GP" + bytes([0, 1]) + struct.pack("<i", 4326) + body


def make_gpkg(path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE gpkg_geometry_columns (table_name, column_name)")
    con.execute("INSERT INTO gpkg_geometry_columns VALUES ('roads', 'geom')")
    con.execute("CREATE TABLE roads (fid INTEGER PRIMARY KEY, geom BLOB, highway, oneway, adm1_name, adm2_name)")
    con.executemany("INSERT INTO roads (geom, highway, oneway, adm1_name, adm2_name) VALUES (?,?,?,?,?)", rows)
    con.commit(); con.close()


# 위도 36.0 위를 동쪽으로 0.01° 간격으로 놓인 노드 1~5 (1→3 primary, 3→5 primary_link 제한속도 30), 3→6 일방통행
LINE = [
    (_gp_line([(LON0, 36.0), (LON0 + .01, 36.0), (LON0 + .02, 36.0)]), "primary", None, "North Gyeongsang", "Andong-si"),
    (_gp_line([(LON0 + .02, 36.0), (LON0 + .03, 36.0), (LON0 + .04, 36.0)]), "primary_link", None, "North Gyeongsang", "Andong-si"),
    (_gp_line([(LON0 + .02, 36.0), (LON0 + .02, 36.01)]), "residential", "yes", "Gangwon", "Uljin-gun"),
    (_gp_line([(LON0 + .04, 36.0), (LON0 + .05, 36.02)]), "footway", None, "North Gyeongsang", "Andong-si"),
]


@pytest.fixture
def graph(tmp_path):
    p = tmp_path / "roads.gpkg"
    make_gpkg(p, LINE)
    c = hotosm.read_roads(p, [35.9, 128.9, 36.1, 129.2], ["primary", "residential"])
    return hotosm.to_graph(c), c


def K(lon, lat=36.0):
    return hotosm.node_key(lat, lon)


def test_utmk_matches_pyproj_reference_values():
    for (lat, lon), (x, y) in [((37.5665, 126.9780), (953901.165, 1952032.081)), ((35.1796, 129.0756), (1143467.380, 1688281.982)),
                               ((33.4996, 126.5312), (910010.546, 1501279.789)), ((37.48, 130.90), (1300652.575, 1947739.115))]:
        X, Y = to_utmk(lat, lon)
        assert X == pytest.approx(x, abs=0.01) and Y == pytest.approx(y, abs=0.01)
        assert to_wgs84(X, Y) == pytest.approx((lat, lon), abs=1e-8)
    assert to_utmk(38.0, 127.5) == pytest.approx((1_000_000.0, 2_000_000.0))


def test_haversine_and_point_index():
    assert 890 < haversine_m(36.0, 129.0, 36.0, 129.01) < 910
    idx = PointIndex({"a": (36.0, 129.0), "b": (36.0, 129.02)})
    assert idx.nearest(36.0, 129.004, 1000)[0] == "a" and idx.nearest(36.0, 129.05, 1000) is None


def test_multi_source_dijkstra_and_largest_component():
    g = RoadGraph(nodes={i: (0, i) for i in range(7)})
    for a in range(4):
        g.add_edge(a, a + 1, 10); g.add_edge(a + 1, a, 10)
    g.add_edge(5, 6, 1)
    best = multi_source_dijkstra(g, {0: 0, 4: 5})
    assert best[1] == (10, 0) and best[3] == (15, 4) and best[2] == (20, 0)
    assert set(multi_source_dijkstra(g, {0: 0}, cutoff=15)) == {0, 1}
    assert set(g.largest_component().nodes) == {0, 1, 2, 3, 4}


def test_hotosm_reads_graph_with_speeds_oneway_and_regions(graph):
    g, c = graph
    assert len(c["ways"]) == 3                                         # 보도(footway)는 빠짐
    t12 = dict(g.adj[K(LON0)])[K(LON0 + .01)]
    assert t12 == pytest.approx(haversine_m(36, LON0, 36, LON0 + .01) / (50 / 3.6))
    t34 = dict(g.adj[K(LON0 + .02)])[K(LON0 + .03)]
    assert t34 == pytest.approx(haversine_m(36, LON0 + .02, 36, LON0 + .03) / (50 / 3.6))   # primary_link 도 primary 속도 (제한속도 열 없음)
    up = K(LON0 + .02, 36.01)
    assert up in dict(g.adj[K(LON0 + .02)]) and K(LON0 + .02) not in dict(g.adj[up])         # 일방통행
    regs = regions.node_regions(c)
    assert regs[K(LON0)] == "안동시" and regs[up] == "울진군"


def test_regions_fixes():
    assert regions.sido_ko("North Gyeongsang") == "경상북도" and len(regions.SIDO) == 17
    assert regions.fix_admin("Gangwon", "Uljin-gun") == ("경상북도", "울진군")
    assert regions.fix_admin("North Gyeongsang", "Gunwi-gun") == ("대구광역시", "군위군")
    assert regions.gyeongbuk_sigun("North Gyeongsang", "Buk-gu") == "포항시"
    assert regions.gyeongbuk_sigun("North Gyeongsang", "Dalseong-gun") is None
    assert regions.fix_admin("Seoul", "Jongno-gu") == ("서울특별시", "Jongno-gu")


def test_access_network_coverage_bands_and_vulnerable(graph):
    g, _ = graph
    fac = [{"name": "동쪽", "lat": 36.0, "lon": LON0 + .04, "tier": "center"}, {"name": "서쪽", "lat": 36.0, "lon": LON0, "tier": "small"}]
    cells = [{"lat": 36.0, "lon": LON0 + .001, "pop": 1000}, {"lat": 36.0, "lon": LON0 + .039, "pop": 500}, {"lat": 36.3, "lon": LON0, "pop": 200}]
    net = access.Network(g, cells, snap_m=1500, access_kmh=20)
    mins, near, info = net.travel_times(fac, ["center"])
    assert near == [0, 0, None] and mins[2] is None and info["cells_no_road"] == 1
    assert mins[1] < 1 < mins[0]
    cov = access.coverage(cells, mins, 3)
    assert (cov["within"], cov["population"], cov["population_unreached"]) == (500, 1700, 200)
    assert sum(b["pop"] for b in access.bands(cells, mins)) == 1700
    assert access.weighted_median(cells, mins) is not None
    v = access.vulnerable({"A": {"share_within": 0.6}}, [{"name": "A", "vulnerability": True}, {"name": "B", "vulnerability": True}])
    assert v["is_vulnerable"] is True and v["missing"] == ["B"]


def test_hotspot_finds_planted_cluster_and_fdr_controls_noise():
    rng = np.random.default_rng(7)
    bg = list(zip(1_000_000 + rng.uniform(0, 40_000, 1500), 1_800_000 + rng.uniform(0, 40_000, 1500)))
    cx, cy = 1_020_500, 1_820_500
    cl = list(zip(cx + rng.normal(0, 300, 60), cy + rng.normal(0, 300, 60)))
    g = hotspot.make_grid([{"x": x, "y": y} for x, y in bg + cl], 1000)
    z = hotspot.gi_star(g, 1500)
    zs = hotspot.zones(g, hotspot.bh_hot(z, 0.05), z)
    x, y = to_utmk(zs[0]["lat"], zs[0]["lon"])
    assert abs(x - cx) < 1000 and abs(y - cy) < 1000 and zs[0]["crashes"] >= 60
    rng2 = np.random.default_rng(11)
    g2 = hotspot.make_grid([{"x": a, "y": b} for a, b in zip(1e6 + rng2.uniform(0, 4e4, 3000), 1.8e6 + rng2.uniform(0, 4e4, 3000))], 1000)
    z2 = hotspot.gi_star(g2, 1500)
    assert (z2 > 1.645).sum() > 20 and hotspot.bh_hot(z2, 0.05).sum() <= 3


def test_public_api():
    import krgeo
    assert krgeo.__version__ == "0.1.0" and callable(krgeo.to_utmk) and krgeo.RoadGraph
