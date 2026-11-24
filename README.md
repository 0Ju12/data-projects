# data-projects — 공개 데이터로 만든 데이터·AI 프로젝트 모음

에너지·자원·제조·금융 분야의 **공개 데이터**로 수집 → 정제 → 분석·모델링 → 검증까지 직접 해 본 프로젝트 9개입니다.
각 폴더가 독립된 프로젝트이고, 폴더마다 README·테스트가 따로 있습니다.

| 폴더 | 내용 | 데이터 | 핵심 결과 |
|---|---|---|---|
| [geo-data-pipeline](geo-data-pipeline/) | 지진 목록 증분 수집·정제·b값 분석·[3D 지진 지도](https://0ju12.github.io/data-projects/) (진원을 실제 깊이에 표시), 매일 자동 갱신 | USGS FDSN (2,474건) | 동아시아 M4+ b = 1.11 ± 0.05 · 수정본 교체·격리 집계 |
| [sensor-anomaly](sensor-anomaly/) | 유압 설비 부품별 이상 탐지·스트리밍 경보·지도학습 진단 | UCI 유압 설비 (2,205 사이클 × 17 센서) | 무작위 분할 0.99 → 시간 구간 분할에서 RF 0.46, LDA 1.00 (밸브) |
| [power-demand](power-demand/) | 하루 전 전국 시간별 전력 수요 예측 · [예측 탐색기](https://0ju12.github.io/data-projects/power/) | 전력거래소 2025 시간별 수요 + 기온 | 앙상블 MAPE 3.23% · 일 최대수요 2.64% |
| [dart-analyzer](dart-analyzer/) | 전자공시 데이터 마트(SQL 뷰)와 사업보고서 근거 검색 | OpenDART | 피벗·LAG·RANK 뷰, 2-gram BM25 근거 검색 (인증키로 실행) |
| [wildfire-watch](wildfire-watch/) | 화재기상지수(FFWI)와 위성 화재 탐지를 매일 모아 비교 · [산불 위험 3D 지도](https://0ju12.github.io/data-projects/fire/) | NASA FIRMS VIIRS + Open-Meteo | 탐지의 90%는 제철소 등 상시 열원 → 가려내는 규칙 · 지수 평가는 아직 표본 부족(AUC 0.57, 양성 10건) |
| [data-agent](data-agent/) | 위 결과들을 LLM이 SQL로 조회하는 MCP 서버 + 답 속 숫자 검증 | 이 저장소의 산출물 (SQLite) | 읽기 전용 SQL 안전장치 · 틀린 숫자·지어낸 계산을 막는 검사 (LLM 연결 평가는 미실시) |
| [warehouse](warehouse/) | 2025년 전력 수요·기온·일사량과 데이터 직무 채용 공고로 질문 8개를 세우고 dbt 분석 표로 답함 · [분석 대시보드](https://0ju12.github.io/data-projects/warehouse/) | 전력거래소 수요 · Open-Meteo 기온·일사량 · Remote OK·Arbeitnow 공고 (+ 부가: 지진·재해 경보·시세·패키지 통계) | 평일 기온 17.5℃ 위 1℃당 +1,636 MW · 13℃ 아래 +969 MW (R² 0.83) · 쉬는 날 −10.8~16.7% · 일사량 100 W/m²당 한낮 수요 −2,704 MW (해가 진 20~23시 대조군 +11 MW) · 직무별 기술 언급률 · 모델 44개(분석 표 12개) · dbt 테스트 129개 |
| [energy-transition](energy-transition/) | 한국 발전 구성 25년·석탄 감소 속도·태양광 계절성·탄소 집약도를 12개국과 비교 · [대시보드](https://0ju12.github.io/data-projects/energy/) | Ember 월별 발전량 · Our World in Data 연간 에너지 (CC BY, 키 없음) | 석탄 46.3%(2009) → 31.1%(2025) · 태양광 5월 7.6% vs 12월 3.4% · D3 연도 재생 산점도 · SQL 쿼리 7개 |
| [api-watch](api-watch/) | API 응답·최신성·구조·품질 관제 + 하루 한 개 AI 기술 학습 · [관제판](https://0ju12.github.io/data-projects/api-watch/) | 22개 공개 엔드포인트 · 한국·글로벌 API/리소스 전체 탐색 · 공식 GitHub/Hugging Face 메타데이터 | 실제 검사와 합성 장애 10종을 분리 · Django/PostgreSQL 실행 구성 · 정기 검사 표본을 가동률로 일반화하지 않음 |

벡터 검색 구현과 한국어 근거 검색 평가는 [VectorLab](vector-search/)에서 실행할 수 있습니다.

진행 중 (뼈대 단계 — 엔진·테스트만 있고 실제 자료로 낸 결과는 아직 없음)
- [er-access](er-access/): 1 km 격자마다 가장 가까운 응급실까지의 차량 이동 시간을 OSM 도로망(HOT 한국 내보내기)으로 계산해 경북의 응급의료 취약 인구를 셉니다. deck.gl 3D 지도(높이 = 인구, 색 = 이동 시간) · [응급실 접근성 3D 지도](https://0ju12.github.io/data-projects/er/). 공식 응급실 목록을 받기 전이라 임시 목록(권역센터 5곳 + OSM 12곳)으로 낸 첫 결과: 권역센터 60분 안 91.8%, 영양·문경·봉화·울진이 낮음.
- [crash-hotspots](crash-hotspots/): 사망 교통사고 지점을 UTM-K 1 km 격자에 모아 Getis-Ord Gi\* 와 거짓 발견 비율 보정(BH)으로 우연보다 많이 몰린 구간을 찾고, 공식 사고 다발 지역과 대조합니다.

공통으로 지킨 것
- **평가를 정직하게**: 시계열은 시간 순서로 나눠 검증하고, 잘 안 된 결과(부품별 비지도 탐지의 오경보, 연휴 다음 날 예측 오차)도 README에 남겼습니다.
- **재처리 안전성**: 같은 데이터를 여러 번 넣어도 결과가 같게(멱등), 원본은 체크섬으로 확인.
- **비밀값 관리**: 인증키는 환경변수·GitHub Secrets로만 받습니다.

```bash
cd <폴더> && python -m pytest -q     # geo 11 · sensor 6 · power 5 · dart 17 · wildfire 8 · agent 16 · warehouse 42 · energy 5 · er-access 19 · crash 12
```

GitHub Actions: `tests`(폴더별 테스트 + Airflow DAG 1회 실행), `geo daily update`(매일 수집 → 지진 대시보드·산불 위험 지도·분석 웨어하우스·전력 전환 대시보드를 갱신하고 전력 예측 탐색기·API 관제판과 함께 GitHub Pages로 배포), `dart build mart`(인증키가 있을 때 매월).

데이터 출처·라이선스는 각 폴더 README에 적었습니다 (USGS 공공 데이터, UCI CC BY 4.0, 공공데이터포털, Open-Meteo CC BY 4.0, OpenDART).
