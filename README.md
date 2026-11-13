# data-projects — 공개 데이터로 만든 데이터·AI 프로젝트 모음

에너지·자원·제조·금융 분야의 **공개 데이터**로 수집 → 정제 → 분석·모델링 → 검증까지 직접 해 본 프로젝트 7개입니다.
각 폴더가 독립된 프로젝트이고, 폴더마다 README·테스트가 따로 있습니다.

| 폴더 | 내용 | 데이터 | 핵심 결과 |
|---|---|---|---|
| [geo-data-pipeline](geo-data-pipeline/) | 지진 목록 증분 수집·정제·b값 분석·[지도 대시보드](https://0ju12.github.io/data-projects/), 매일 자동 갱신 | USGS FDSN (2,474건) | 동아시아 M4+ b = 1.11 ± 0.05 · 수정본 교체·격리 집계 |
| [sensor-anomaly](sensor-anomaly/) | 유압 설비 부품별 이상 탐지·스트리밍 경보·지도학습 진단 | UCI 유압 설비 (2,205 사이클 × 17 센서) | 무작위 분할 0.99 → 시간 구간 분할에서 RF 0.46, LDA 1.00 (밸브) |
| [power-demand](power-demand/) | 하루 전 전국 시간별 전력 수요 예측 · [예측 탐색기](https://0ju12.github.io/data-projects/power/) | 전력거래소 2025 시간별 수요 + 기온 | 앙상블 MAPE 3.23% · 일 최대수요 2.64% |
| [dart-analyzer](dart-analyzer/) | 전자공시 데이터 마트(SQL 뷰)와 사업보고서 근거 검색 | OpenDART | 피벗·LAG·RANK 뷰, 2-gram BM25 근거 검색 (인증키로 실행) |
| [wildfire-watch](wildfire-watch/) | 화재기상지수(FFWI)와 위성 화재 탐지를 매일 모아 비교 · [산불 위험 지도](https://0ju12.github.io/data-projects/fire/) | NASA FIRMS VIIRS + Open-Meteo | 탐지의 90%는 제철소 등 상시 열원 → 가려내는 규칙 · 지수 평가는 아직 표본 부족(AUC 0.57, 양성 10건) |
| [data-agent](data-agent/) | 위 결과들을 LLM 이 SQL 로 조회하는 MCP 서버 + 답 속 숫자 검증 | 이 저장소의 산출물 (SQLite) | 읽기 전용 SQL 안전장치 · 틀린 숫자·지어낸 계산을 막는 검사 (LLM 연결 평가는 미실시) |
| [warehouse](warehouse/) | 위 자료를 dbt 로 3단 모델링(원본→정제→집계)하고 Airflow DAG 로 실행 · [상태 보고서](https://0ju12.github.io/data-projects/warehouse/) | 이 저장소의 지진·수요·기온 자료 + 채용 공고 공개 피드 (DuckDB) | 품질 테스트 58개 · 지진 수정 이력 보존(SCD 2형) · 증분 집계와 전체 재계산 일치 확인 · 채용 공고 기술 수요 집계 (자료가 작아 성능은 다루지 않음) |

공통으로 지킨 것
- **평가를 정직하게**: 시계열은 시간 순서로 나눠 검증하고, 잘 안 된 결과(부품별 비지도 탐지의 오경보, 연휴 다음 날 예측 오차)도 README 에 남겼습니다.
- **재처리 안전성**: 같은 데이터를 여러 번 넣어도 결과가 같게(멱등), 원본은 체크섬으로 확인.
- **비밀값 관리**: 인증키는 환경변수·GitHub Secrets 로만 받습니다.

```bash
cd <폴더> && python -m pytest -q     # geo 11 · sensor 6 · power 5 · dart 17 · wildfire 8 · agent 16 · warehouse 26
```

GitHub Actions: `tests`(폴더별 테스트 + Airflow DAG 1회 실행), `geo daily update`(매일 수집 → 지진 대시보드·산불 위험 지도를 갱신하고 전력 예측 탐색기와 함께 GitHub Pages 로 배포), `dart build mart`(인증키가 있을 때 매월).

데이터 출처·라이선스는 각 폴더 README 에 적었습니다 (USGS 공공 데이터, UCI CC BY 4.0, 공공데이터포털, Open-Meteo CC BY 4.0, OpenDART).
