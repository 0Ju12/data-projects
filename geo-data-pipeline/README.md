# geo-data-pipeline — 동아시아 지진 데이터 파이프라인

공개 지진 목록(USGS FDSN Event API)을 **매일 수집 → 정제 → 저장 → 분석 → 대시보드로 공개**하는 작은 데이터 파이프라인입니다.
지구물리 석사 과정에서 다룬 자료 해석을 데이터 엔지니어링 흐름(증분 수집·재처리 안전성·품질 검사·자동화)으로 옮겨 본 프로젝트입니다.

- 대시보드: GitHub Pages `docs/index.html` (지도, 월별 건수, 규모-누적빈도와 b값, 깊이 분포, 큰 지진, 데이터 품질)
- 외부 라이브러리 없이 Python 표준 라이브러리만 사용 (테스트에만 pytest)

## 흐름

```
USGS FDSN API ──fetch──▶ GeoJSON ──clean──▶ events.csv (원본, diff 가능) ──▶ events.sqlite (질의용, 매번 재생성)
     ▲ 지역별 마지막 실행 3일 전부터 다시 받음            │
     │ (늦게 올라오는 수정본까지 반영)                    └──analyze──▶ summary.json ──render──▶ docs/index.html
GitHub Actions 매일 06:17 KST ─────────────────────────────────────────────────────────────▶ 커밋 → Pages
```

## 설계 판단

| 문제 | 선택 |
|---|---|
| 같은 지진의 위치·규모가 나중에 수정됨 | id 기준으로 합치고 `updated` 가 더 늦은 수정본만 교체. 오래된 수정본이 늦게 와도 덮어쓰지 않음 |
| 매일 실행 시 누락 | 마지막 실행 3일 전부터 겹쳐 받음 → 같은 데이터를 여러 번 넣어도 결과가 같음(멱등) |
| 한 번에 최대 20,000건 | 먼저 `count` 로 건수를 보고 많으면 기간을 반으로 나눠 다시 요청 |
| 이상한 레코드 | 규모 없음·좌표/깊이 범위 밖·지진이 아닌 이벤트(발파 등)는 저장하지 않고 **개수만 품질 보고서에 남김** |
| 네트워크 실패 | 지수 백오프로 4번 재시도 후 예외. 빈 결과로 저장하지 않아 '데이터 없음'과 '실패'가 구분됨 |
| 지역마다 관측 수준이 다름 | 지역별로 최소 규모·시작일을 따로 수집. 한반도는 M2.5+ (2016~), 동아시아는 M4.0+ (2023.11~) |

## 분석 (2026-11-10 실행 결과)

| 지역 | 이벤트 | b값 (Mc) |
|---|---|---|
| 동아시아 M4.0+ (2023.11~) | 2,446 | 1.11 ± 0.05 (Mc 4.6, n = 742) |
| 일본 동북 앞바다 M4.0+ | 1,120 | 1.13 ± 0.06 (Mc 4.5, n = 476) |
| 한반도 주변 M2.5+ (2016~) | 30 | 이벤트가 적어 추정하지 않음 |

- b값: 완전성 규모 Mc 를 최대 곡률법(+0.2 보정)으로 정하고 Aki–Utsu 최우추정, 오차는 Shi & Bolt (1982).
- 테스트에서 b = 1 인 합성 규모 5,000개로 추정값이 1 ± 0.06 안에 드는지 확인합니다.
- **한계**: USGS 목록은 지역에 따라 mb·Mww·Mwr 규모가 섞여 있어 b값은 참고 지표입니다. 한반도 소규모 지진은 기상청 목록이 훨씬 촘촘하므로, 국내 분석에는 기상청 자료를 붙이는 것이 다음 단계입니다.
- 한반도 목록에는 2016 경주 지진(Mww 5.4)과 2017 포항 지진(Mww 5.5)이 들어 있습니다. 포항 지진은 정부 조사연구단이 인근 지열발전(EGS) 실증 사업과 관련된 촉발 지진으로 결론 낸 사례로, 학부 때 다룬 Utah FORGE 지열 부지 연구와 이어지는 주제입니다.

## 실행

```bash
python -m geopipe.cli run                      # 증분 수집 (처음이면 config.json 의 시작일부터)
python -m geopipe.cli run --offline tests/fixtures/usgs_sample.geojson --data /tmp/d --docs /tmp/d   # 네트워크 없이
python -m pytest -q                            # 테스트 11개
```

## 구성

```
geopipe/fetch.py      USGS API (count → 기간 분할, 재시도)
geopipe/transform.py  정제·중복/수정본 처리·격리 집계, UTC/KST
geopipe/store.py      CSV ⇄ SQLite, 실행 상태
geopipe/analyze.py    월별 건수(빈 달 0), 규모-누적빈도, b값·Mc, 깊이 분포
geopipe/dashboard.py  정적 HTML (Leaflet 지도 + 서버에서 그린 SVG)
config.json           지역(경계·최소 규모·수집 시작일)
```

데이터: U.S. Geological Survey, Earthquake Hazards Program. 지도: © OpenStreetMap contributors.
