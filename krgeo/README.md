# krgeo

한국 공간 데이터를 다룰 때 매번 다시 짜던 코드를 모은 파이썬 패키지입니다.
[er-access](../er-access)(응급실 접근성)와 [crash-hotspots](../crash-hotspots)(교통사고 핫스팟)에서 쓰던 코드를 떼어 내 테스트와 함께 정리했습니다.

- 핵심 기능은 **표준 라이브러리만** 씁니다 (sqlite3 로 GeoPackage 를 읽고, 다익스트라도 직접 구현). GDAL·pyproj·networkx 가 필요 없습니다.
- 핫스팟 통계만 numpy 가 필요합니다: `pip install "krgeo[stats]"`

```bash
pip install "git+https://github.com/0Ju12/data-projects#subdirectory=krgeo"
```

| 모듈 | 하는 일 |
|---|---|
| `krgeo.utmk` | UTM-K(EPSG:5179) ↔ WGS84 변환. pyproj 결과와 0.01 m 안쪽으로 일치 (테스트에 기준값) |
| `krgeo.geo` | 하버사인 거리, 격자 색인으로 가장 가까운 점 찾기 |
| `krgeo.graph` | 방향 있는 도로 그래프, 여러 출발점 다익스트라, 가장 큰 연결 요소 |
| `krgeo.hotosm` | [HOT 국가별 OSM 내보내기](https://data.humdata.org/dataset/hotosm_kor_roads)의 도로 GeoPackage → 이동 시간 그래프 (도로 등급별 속도, 제한속도, 일방통행) |
| `krgeo.regions` | 시도 한글 이름, HOT 행정구역 표시 오류 보정 (울진군 → 경북, 군위·달성·수성 → 대구, 경북 Buk-gu → 포항) |
| `krgeo.access` | 격자 접근성: 칸마다 가장 가까운 시설까지 몇 분인지, 기준 시간 안 인구 비율, 시간대별 인구, 인구 가중 중앙값 |
| `krgeo.hotspot` | 격자 Getis-Ord Gi* + Benjamini–Hochberg 거짓 발견 비율 보정, 붙은 칸을 구역으로 묶기 |

## 예시

```python
from krgeo import to_utmk, to_wgs84
x, y = to_utmk(37.5665, 126.9780)          # (953901.17, 1952032.08)

from krgeo import hotosm, regions, access
roads = hotosm.read_roads("hotosm_kor_roads_lines_gpkg.gpkg",
                          bbox=[35.5, 128.0, 37.6, 131.0],          # 남, 서, 북, 동
                          classes=["motorway", "trunk", "primary", "secondary", "tertiary", "residential"])
g = hotosm.to_graph(roads).largest_component()
where = regions.node_regions(roads)        # 노드 → '안동시' 같은 경북 시군 (경북 밖은 None)

cells = [{"lat": 36.57, "lon": 128.73, "pop": 1200}, ...]
hospitals = [{"name": "안동병원", "lat": 36.56, "lon": 128.70, "tier": "center"}, ...]
net = access.Network(g, cells, snap_m=1500, access_kmh=20)
minutes, nearest, info = net.travel_times(hospitals, tiers=["center"])
access.coverage(cells, minutes, 30)        # {'within': ..., 'population': ..., 'share': ...}
```

```python
from krgeo import hotspot                  # pip install "krgeo[stats]"
grid = hotspot.make_grid([{"x": x, "y": y} for x, y in crash_points_utmk], cell=500)
z = hotspot.gi_star(grid, band_m=750)
zones = hotspot.zones(grid, hotspot.bh_hot(z, q=0.05), z)   # 가장 강한 구역부터
```

## 개발

```bash
pip install -e ".[test]"
python -m pytest -q
```

태그 `krgeo-v*` 를 올리면 CI 가 wheel 을 만들어 PyPI 신뢰할 수 있는 게시자(trusted publishing)로 올립니다.
PyPI 에 이 저장소를 게시자로 등록해 두어야 동작합니다 (아직 하지 않음).

MIT 라이선스.
