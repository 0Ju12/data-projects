import zipfile
from pathlib import Path

import pytest

from eraccess import access, er, osm, population
from eraccess.geo import PointIndex, haversine_m
from eraccess.graph import RoadGraph, multi_source_dijkstra

# 위도 36.0 위를 동쪽으로 0.01° (약 900 m) 간격으로 놓인 노드 1~5. 6 은 일방통행으로만 이어진 곁가지.
LON0 = 129.00


def node(i, lon, lat=36.0):
    return {"type": "node", "id": i, "lat": lat, "lon": lon}


OVERPASS = {"elements": [
    *(node(i, LON0 + 0.01 * (i - 1)) for i in range(1, 6)),
    node(6, LON0 + 0.02, 36.01),
    node(7, LON0 + 0.05, 36.02),
    {"type": "way", "id": 100, "nodes": [1, 2, 3], "tags": {"highway": "primary"}},
    {"type": "way", "id": 101, "nodes": [3, 4, 5], "tags": {"highway": "primary_link", "maxspeed": "30"}},
    {"type": "way", "id": 102, "nodes": [3, 6], "tags": {"highway": "residential", "oneway": "yes"}},
    {"type": "way", "id": 103, "nodes": [5, 7], "tags": {"highway": "footway"}},          # 차도 아님 → 빠짐
]}


def test_haversine_and_point_index():
    d = haversine_m(36.0, 129.0, 36.0, 129.01)
    assert 890 < d < 910
    idx = PointIndex({"a": (36.0, 129.0), "b": (36.0, 129.02)})
    assert idx.nearest(36.0, 129.004, 1000)[0] == "a"
    assert idx.nearest(36.0, 129.015, 1000)[0] == "b"
    assert idx.nearest(36.0, 129.05, 1000) is None                     # 거리 제한 밖


def test_osm_graph_speeds_and_oneway():
    g = osm.to_graph(OVERPASS)
    assert 7 not in g.nodes                                             # 보도는 그래프에 없음
    t12 = dict(g.adj[1])[2]
    assert t12 == pytest.approx(haversine_m(36, LON0, 36, LON0 + 0.01) / (50 / 3.6))
    t34 = dict(g.adj[3])[4]
    assert t34 == pytest.approx(haversine_m(36, LON0 + 0.02, 36, LON0 + 0.03) / (30 / 3.6))   # 제한속도 30 이 가정 50 보다 낮음
    assert 6 in dict(g.adj[3]) and 3 not in dict(g.adj[6])               # 일방통행
    assert osm._direction({"highway": "motorway"}) == 1
    assert osm._direction({"highway": "motorway", "oneway": "no"}) == 0
    assert osm._direction({"highway": "secondary", "oneway": "-1"}) == -1


def test_build_query():
    q = osm.build_query([35.5, 127.8, 37.5, 129.6], ["primary", "secondary"])
    assert '"^(primary|secondary)(_link)?$"' in q and "(35.5,127.8,37.5,129.6)" in q


def test_multi_source_dijkstra_picks_nearest_source():
    g = RoadGraph(nodes={i: (0, i) for i in range(5)})
    for a in range(4):
        g.add_edge(a, a + 1, 10)
        g.add_edge(a + 1, a, 10)
    best = multi_source_dijkstra(g, {0: 0, 4: 5})
    assert best[1] == (10, 0) and best[3] == (15, 4)
    assert best[2] == (20, 0)                                           # 0 에서 20, 4 에서 25
    cut = multi_source_dijkstra(g, {0: 0}, cutoff=15)
    assert set(cut) == {0, 1}


def test_reversed_graph_follows_oneway_backwards():
    g = osm.to_graph(OVERPASS)
    # 응급실이 6 에 있으면: 3 → 6 으로 갈 수 있으니 3 은 닿고, 6 → 3 은 없으니 원래 그래프에서 6 출발로는 3 에 못 감
    to_er = multi_source_dijkstra(g.reversed(), {6: 0})
    assert 3 in to_er and 1 in to_er
    from_er = multi_source_dijkstra(g, {6: 0})
    assert set(from_er) == {6}


def write_cp949(path: Path, text: str):
    path.write_bytes(text.encode("cp949"))


def test_er_load_cp949_aliases_dedup_and_tiers(tmp_path):
    p = tmp_path / "er.csv"
    write_cp949(p, "기관명,응급의료기관 종별,위도,경도\n"
                   "가 병원,권역응급의료센터,36.0,129.0\n"
                   "가 병원,권역응급의료센터,36.0,129.0\n"            # 중복
                   "나 의원,지역응급의료기관,36.1,129.1\n"
                   "다 병원,지역응급의료센터,,\n"                      # 좌표 없음
                   "라 병원,기타,10.0,10.0\n")                         # 한국 밖 좌표
    rows = er.load(p)
    assert [r["name"] for r in rows] == ["가 병원", "나 의원"]
    assert [r["tier"] for r in rows] == ["regional", "local_institution"]


def test_er_load_api_style_columns(tmp_path):
    p = tmp_path / "er_api.csv"
    p.write_text("dutyName,dutyEmclsName,wgs84Lat,wgs84Lon\nA,지역응급의료센터,36.2,128.9\n", encoding="utf-8")
    assert er.load(p) == [{"name": "A", "lat": 36.2, "lon": 128.9, "tier": "local_center"}]


def test_er_load_reports_missing_columns(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("이름,주소\nA,서울\n", encoding="utf-8")
    with pytest.raises(ValueError, match="위도"):
        er.load(p)


def test_population_load_from_zip_with_bbox(tmp_path):
    z = tmp_path / "pop.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("ppp_KOR_2020_1km_Aggregated.csv",
                   "X,Y,Z\n129.0,36.0,100.5\n129.5,36.5,0\n130.5,36.0,50\n128.9,35.9,20\n")
    cells = population.load(z, [35.95, 128.95, 36.6, 129.6])
    assert cells == [{"lat": 36.0, "lon": 129.0, "pop": 100.5}]          # 빈 칸·범위 밖 제외


def test_travel_times_and_coverage_end_to_end():
    g = osm.to_graph(OVERPASS)
    ers = [{"name": "동쪽센터", "lat": 36.0, "lon": LON0 + 0.04, "tier": "local_center"},
           {"name": "작은기관", "lat": 36.0, "lon": LON0, "tier": "local_institution"}]
    cells = [{"lat": 36.0, "lon": LON0 + 0.001, "pop": 1000},              # 노드 1 근처
             {"lat": 36.0, "lon": LON0 + 0.039, "pop": 500},               # 노드 5 근처
             {"lat": 36.3, "lon": LON0, "pop": 200}]                       # 도로에서 30 km 넘게 떨어짐
    net = access.Network(g, cells, snap_m=1500, access_kmh=20)
    mins, near, info = net.travel_times(ers, ["local_center"])
    assert near == [0, 0, None] and mins[2] is None and info["cells_no_road"] == 1
    assert mins[1] < 1 < mins[0]                                          # 동쪽 칸이 더 가깝다
    # 노드1→5: primary 1.8 km @50 + link 1.8 km @30 ≈ 5.8 분 (+ 도로 붙이기 몫)
    assert 5.5 < mins[0] < 6.5
    cov = access.coverage(cells, mins, 3)
    assert cov["within"] == 500 and cov["population"] == 1700 and cov["population_unreached"] == 200
    mins_any, near_any, _ = net.travel_times(ers, ["local_center", "local_institution"])
    assert near_any[0] == 1 and mins_any[0] < 1
    b = access.bands(cells, mins)
    assert b[0] == {"label": "0–15분", "pop": 1500} and b[-1] == {"label": "못 닿음", "pop": 200}
    assert sum(x["pop"] for x in b) == 1700


def test_tiles_cover_bbox_without_gaps():
    t = osm.tiles([35.57, 127.80, 36.10, 128.30], 0.25)
    assert len(t) == 3 * 2 and t[0] == [35.57, 127.8, 35.82, 128.05] and t[-1][2:] == [36.1, 128.3]


def test_graph_from_tiles_dedups_shared_ways(tmp_path):
    c = osm.compact(OVERPASS)
    for name in ("a.json", "b.json"):                                     # 경계에 걸친 도로는 두 타일에 다 들어 있다
        (tmp_path / name).write_text(__import__("json").dumps(c), encoding="utf-8")
    g1 = osm.to_graph(OVERPASS)
    g2 = osm.graph_from_tiles([tmp_path / "a.json", tmp_path / "b.json"])
    assert g2.edge_count() == g1.edge_count() and set(g2.nodes) == set(g1.nodes)


def test_er_from_osm_and_save_round_trip(tmp_path):
    data = {"elements": [
        {"type": "node", "id": 1, "lat": 36.0, "lon": 129.0, "tags": {"name": "A병원", "amenity": "hospital"}},
        {"type": "way", "id": 2, "center": {"lat": 36.1, "lon": 129.1}, "tags": {"name": "B", "name:ko": "B병원"}},
        {"type": "way", "id": 3, "tags": {"name": "좌표없음"}}]}
    rows = er.from_osm(data)
    assert [r["name"] for r in rows] == ["A병원", "B병원"]
    rows[0]["tier"] = "regional"
    er.save(rows, tmp_path / "e.csv")
    back = er.load(tmp_path / "e.csv")
    assert [r["tier"] for r in back] == ["regional", "other"] and back[1]["lat"] == 36.1


def test_merge_provisional_prefers_regional_center():
    centers = [{"name": "가 대학병원", "lat": 36.0, "lon": 129.0, "tier": "regional"}]
    osm_rows = [{"name": "가대학교병원", "lat": 36.001, "lon": 129.001, "tier": "other"},    # 약 140 m → 같은 병원
                {"name": "나 병원", "lat": 36.05, "lon": 129.0, "tier": "other"}]
    merged = er.merge_provisional(osm_rows, centers)
    assert [(r["name"], r["tier"]) for r in merged] == [("가 대학병원", "regional"), ("나 병원", "other")]
