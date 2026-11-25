# map-tiles — 공개 데이터를 벡터 타일 파일 하나로

이 저장소의 세 프로젝트 산출물(지진 목록, 산불 위험, 응급실 접근성)을 **벡터 타일(MVT)** 로 잘라 **PMTiles 파일 하나**에 담고,
MapLibre 지도가 그 파일에서 지금 보이는 타일만 HTTP 범위 요청으로 받아 그리게 했습니다. 타일 서버 없이 GitHub Pages 에 올립니다.

[타일 지도](https://0ju12.github.io/data-projects/tiles/) · 매일 지진·산불 갱신 뒤 다시 굽습니다 (`geo daily update`).

## 왜 만들었나

다른 대시보드들은 data.json 을 통째로 받습니다. 응급실 접근성 지도는 1.07 MB, 산불 지도는 0.24 MB 이고 레이어를 더할수록 커집니다.
타일로 나누면 처음 화면에서 받는 양이 전체의 몇 %로 줄고, 확대한 곳만 더 받습니다. 처음 화면에서 2.15 MB 중 60 KB(2.7%)를 받았습니다.

## 구성

| 파일 | 하는 일 |
|---|---|
| `tiles/mvt.py` | Mapbox Vector Tile 2.1 인코더. protobuf 를 직접 씀 (varint, zigzag 좌표, MoveTo/LineTo/ClosePath, 키·값 중복 제거) |
| `tiles/pmtiles.py` | PMTiles v3 작성기. 힐베르트 타일 번호, 같은 내용 타일 한 번만 저장(run length), gzip 목록, 루트 목록이 16 KiB 를 넘으면 잎 목록으로 나눔 |
| `tiles/tiling.py` | 경위도 → 웹 메르카토르 타일 좌표, 점·격자 칸을 걸치는 타일마다 잘라 넣기 (경계 너머 64 단위 겹침) |
| `tiles/build.py` | 세 프로젝트 산출물 → 레이어 5개 → `docs/korea.pmtiles`, `docs/layers.json` |
| `docs/index.html` | MapLibre + pmtiles.js 지도. 레이어 켜고 끄기, 응급실 기준 바꾸기, 받은 양 표시 |

굽기는 **파이썬 표준 라이브러리만** 씁니다 (tippecanoe·GDAL 없음). 테스트에서는 공식 파이썬 구현
([mapbox-vector-tile](https://github.com/tilezen/mapbox-vector-tile), [pmtiles](https://github.com/protomaps/PMTiles/tree/main/python))으로 거꾸로 읽어
좌표·속성·타일 번호·잎 목록이 같은지 확인합니다.

| 레이어 | 원본 | 줌 |
|---|---|---|
| `quakes` | 지진 진앙 (규모·깊이·시각) — geo-data-pipeline | 3–11 |
| `fire_grid` | 오늘 화재기상지수 0.25° 칸 — wildfire-watch | 4–11 |
| `fire_points` | 최근 7일 위성 화재 탐지 (상시 열원 표시) — wildfire-watch | 5–11 |
| `er_cells` | 1 km 칸 인구와 응급실까지 분 (3가지 기준). 줌 6·7 은 4×4·2×2 칸을 합침 (인구 합, 분은 인구 가중 평균) — er-access | 6–11 |
| `er_sites` | 응급실 위치·등급 (임시 목록) — er-access | 5–11 |

## 겪은 문제

- **확대하면 레이어가 사라짐**: 한 소스의 최대 줌은 하나라서, 지진 레이어를 줌 10 까지만 넣었더니 줌 11 타일을 쓰는 순간 지진이 지워졌습니다 → 모든 레이어를 최대 줌까지 넣음.
- **칸 사이 흰 선**: 응급실 칸 중심이 소수 4자리로 반올림돼 있어 `중심 ± 반 칸` 으로 그리면 이웃 칸 사이에 1/8 화소 틈이 생기고, 그 틈이 화소 중심에 걸리는 줄마다 흰 선이 보였습니다.
  중심을 정수 격자 번호로 되돌려 이웃 칸이 같은 경계값을 쓰게 해서 없앴습니다 (테스트 `test_aggregate_snaps_rounded_centers_to_shared_edges`).
- **로컬 확인**: `python -m http.server` 는 범위 요청을 지원하지 않아 pmtiles.js 가 거부합니다. GitHub Pages 는 지원합니다.

## 실행

```bash
pip install -r requirements.txt
python -m pytest -q            # 9개
python -m tiles.build          # docs/korea.pmtiles (약 2.6 MB, 2초)
```

`docs/korea.pmtiles` 는 매일 배포 때 새로 구워서 저장소에는 넣지 않습니다 (.gitignore).

자료: 지진 USGS · 산불 NASA FIRMS, Open-Meteo · 도로 OpenStreetMap(HOT) · 인구 GHSL · 배경 OpenFreeMap.
