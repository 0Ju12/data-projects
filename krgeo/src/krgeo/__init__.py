"""krgeo — 한국 공간 데이터 도구 모음.

- utmk:     UTM-K(EPSG:5179) ↔ WGS84 변환 (pyproj 와 0.1 mm 이내)
- geo:      하버사인 거리, 가장 가까운 점 찾기(격자 색인)
- graph:    도로 그래프, 여러 출발점 다익스트라, 가장 큰 연결 요소
- hotosm:   HOT 국가별 OSM 도로(GeoPackage) → 이동 시간 그래프 (표준 라이브러리 sqlite3)
- regions:  시도 한글 이름, HOT 행정구역 표시 보정 (울진·군위·달성 등)
- access:   격자 접근성 — 칸마다 가장 가까운 시설까지 분, 기준 시간 안 인구, 취약 판정
- hotspot:  격자 Getis-Ord Gi* + Benjamini–Hochberg (numpy 필요: pip install krgeo[stats])
"""
from .utmk import to_utmk, to_wgs84
from .geo import haversine_m, PointIndex
from .graph import RoadGraph, multi_source_dijkstra

__version__ = "0.1.0"
__all__ = ["to_utmk", "to_wgs84", "haversine_m", "PointIndex", "RoadGraph", "multi_source_dijkstra", "__version__"]
