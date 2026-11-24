import json

import numpy as np
import pytest

from crash import cli, hotspot, load
from crash.utmk import to_utmk, to_wgs84

# pyproj (EPSG:4326 → EPSG:5179) 로 구한 기준값
REFERENCE = [
    ((37.5665, 126.9780), (953901.165, 1952032.081)),     # 서울시청
    ((35.1796, 129.0756), (1143467.380, 1688281.982)),    # 부산
    ((33.4996, 126.5312), (910010.546, 1501279.789)),     # 제주
    ((37.4800, 130.9000), (1300652.575, 1947739.115)),    # 울릉도
]


@pytest.mark.parametrize("ll,xy", REFERENCE)
def test_utmk_matches_pyproj_and_round_trips(ll, xy):
    x, y = to_utmk(*ll)
    assert x == pytest.approx(xy[0], abs=0.01) and y == pytest.approx(xy[1], abs=0.01)
    lat, lon = to_wgs84(x, y)
    assert lat == pytest.approx(ll[0], abs=1e-8) and lon == pytest.approx(ll[1], abs=1e-8)


def test_utmk_origin():
    assert to_utmk(38.0, 127.5) == pytest.approx((1_000_000.0, 2_000_000.0))


def test_load_cp949_wgs_columns(tmp_path):
    p = tmp_path / "c.csv"
    p.write_bytes(("발생년월일시,사망자수,사고유형_대분류,도로형태,경도,위도\n"
                   "2023010108,1,차대사람,단일로,126.978,37.5665\n"
                   "2023010210,2,차대차,교차로,,\n"
                   "2023010311,1,차량단독,단일로,10.0,10.0\n").encode("cp949"))
    rows, st = load.load(p)
    assert st == {"file": "c.csv", "rows": 3, "kept": 1, "no_coord": 1, "outside_korea": 1}
    r = rows[0]
    assert r["kind"] == "차대사람" and r["deaths"] == 1 and r["x"] == pytest.approx(953901.165, abs=0.01)


def test_load_utmk_only_columns(tmp_path):
    p = tmp_path / "u.csv"
    p.write_text("발생년월일시,발생위치X(UTMK),발생위치Y(UTMK)\n2022050112,\"1,143,467.38\",1688281.982\n", encoding="utf-8")
    rows, _ = load.load(p)
    assert rows[0]["lat"] == pytest.approx(35.1796, abs=1e-6) and rows[0]["lon"] == pytest.approx(129.0756, abs=1e-6)


def test_load_without_coordinates_fails_loudly(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("발생년월일시,사망자수\n2023010108,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="좌표"):
        load.load(p)


def pts(xy):
    return [{"x": x, "y": y, "deaths": 1} for x, y in xy]


def test_grid_counts_and_offsets():
    g = hotspot.make_grid(pts([(1000, 2000), (1500, 2900), (3100, 2000)]), 1000)
    assert g.counts.shape == (1, 3) and g.counts.tolist() == [[2, 0, 1]]
    assert len(hotspot._offsets(1500, 1000)) == 9          # 자신 + 8 이웃
    assert len(hotspot._offsets(1000, 1000)) == 5          # 자신 + 상하좌우


def background(rng, n, size_m=40_000):
    return list(zip(1_000_000 + rng.uniform(0, size_m, n), 1_800_000 + rng.uniform(0, size_m, n)))


def test_gi_star_finds_planted_cluster():
    rng = np.random.default_rng(7)
    bg = background(rng, 1500)                                       # 40×40 km 에 고르게 1,500건
    cx, cy = 1_020_500, 1_820_500
    cluster = list(zip(cx + rng.normal(0, 300, 60), cy + rng.normal(0, 300, 60)))   # 한 지점에 60건
    g = hotspot.make_grid(pts(bg + cluster), 1000)
    z = hotspot.gi_star(g, 1500)
    hot = hotspot.bh_hot(z, 0.05)
    zs = hotspot.zones(g, hot, z)
    assert len(zs) >= 1
    top = zs[0]
    x, y = to_utmk(top["lat"], top["lon"])
    assert abs(x - cx) < 1000 and abs(y - cy) < 1000                # 가장 큰 구역 = 심어 둔 곳
    assert top["crashes"] >= 60


def test_uniform_noise_gives_almost_no_hotspots_after_fdr():
    rng = np.random.default_rng(11)
    g = hotspot.make_grid(pts(background(rng, 3000)), 1000)
    z = hotspot.gi_star(g, 1500)
    raw = int((z > 1.645).sum())                                   # 보정 없이 단측 0.05
    fdr = int(hotspot.bh_hot(z, 0.05).sum())
    assert raw > 20                                                 # 보정 없으면 우연한 핫스팟이 꽤 나온다
    assert fdr <= 3                                                 # BH 뒤에는 거의 없다


def test_build_end_to_end(tmp_path, monkeypatch):
    rng = np.random.default_rng(3)
    data = tmp_path / "data"
    data.mkdir()
    lines = ["발생년월일시,사망자수,발생위치X(UTMK),발생위치Y(UTMK)"]
    for x, y in background(rng, 800) + [(1_010_500 + dx, 1_810_500 + dy) for dx, dy in rng.normal(0, 250, (40, 2))]:
        lines.append(f"2024010100,1,{x:.1f},{y:.1f}")
    (data / "crashes_2024.csv").write_text("\n".join(lines), encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "DATA", data)
    s = cli.build({"region": "시험", "inputs": "data/crashes_*.csv", "cell_m": 1000, "band_m": 1500, "fdr_q": 0.05})
    assert s["crashes"] == 840 and s["zones"] >= 1 and s["top_zones"][0]["crashes"] >= 40
    assert json.loads((data / "summary.json").read_text(encoding="utf-8"))["crashes"] == 840
