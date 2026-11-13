# warehouse — 수집한 자료를 dbt 로 모델링하고 Airflow 로 돌리기

같은 저장소의 다른 프로젝트가 모으는 자료(지진 목록 · 전력 수요 · 기온)와 직접 모으는 채용 공고를 **원본 → 정제 → 집계** 3단으로 정리하고,
품질 테스트·변경 이력·재실행 안전성·실행 기록까지 갖춘 작은 데이터 웨어하우스입니다.

- 상태 보고서(계보·테스트 결과·실행 기록): <https://0ju12.github.io/data-projects/warehouse/> — 매일 06:17 KST 실행 뒤 갱신
- 도구: dbt-core + DuckDB, Airflow 3 (DAG), GitHub Actions(매일 실행), pytest

## 구조

```
demand.csv ─ stg_demand_wide ─ int_demand_hourly ─┬─ fct_demand_hourly ─ fct_demand_daily
weather.csv ─ stg_weather ────────────────────────┘        └ dim_date
quakes.csv ─ stg_quakes ─┬─ dim_region · fct_quakes_monthly
                         └─ snap_quakes (변경 이력, SCD 2형)
```

| 층 | 모델 | 하는 일 |
|---|---|---|
| staging (view) | `stg_quakes` `stg_demand_wide` `stg_weather` | 이름·형 정리만. 원본 파일은 복사하지 않고 그대로 읽음 |
| intermediate (view) | `int_demand_hourly` | 날짜 × 24열 표를 시간별 행으로 풀기 |
| marts (table) | `dim_date` `dim_region` `fct_demand_hourly` `fct_demand_daily` `fct_quakes_monthly` | 차원·사실 표 |
| snapshot | `snap_quakes` | USGS 가 규모·위치·상태를 고친 이력 보존 |

## 직접 정한 것

**"24시"를 다음 날 0시로 넘기지 않는다.** 전력거래소 자료의 `24시` 는 그날 23:00~24:00 구간의 평균입니다.
끝나는 시각을 키로 쓰면 하루의 마지막 행이 다음 날짜로 넘어가 날짜별 집계가 한 시간씩 밀립니다.
그래서 **시작 시각**(`hour_start_kst`)을 키로 삼았고, `tests/assert_24_hours_per_day.sql`·`assert_no_hour_gaps.sql` 로 지킵니다.

**고쳐진 지진은 덮어쓰지 않고 판을 쌓는다.** 지진은 발생 직후 자동 산정값(`automatic`)으로 올라왔다가 검토 뒤 값이 바뀝니다.
`snap_quakes` 는 `updated_at` 이 바뀐 행의 이전 판을 닫고 새 판을 추가하므로 "그날에는 얼마로 알려져 있었나"를 되물을 수 있습니다.
CI 는 매번 빈 DB 에서 시작하기 때문에 이력 표를 `state/snap_quakes.parquet` 로 저장소에 남기고, 실행 전에 되살려 이어 쌓습니다.

**같은 날짜를 몇 번 돌려도 결과가 같다.** 날짜 파티션 내보내기는 임시 파일에 쓴 뒤 바꿔치기하고 정렬·압축을 고정해, 다시 돌리면 같은 해시의 파일이 나옵니다.
실행 기록도 같은 날짜 줄을 바꿔 쓰므로 재실행해도 줄이 늘지 않습니다.

**월별 지진 집계는 바뀐 묶음만 다시 계산한다(증분).** `fct_quakes_monthly` 는 지난 실행 뒤에 새로 들어오거나 고쳐진 지진이 속한 (월, 지역)만 다시 계산해 바꿔 넣습니다.
기준은 발생 시각이 아니라 **수정 시각**입니다 — 발생 시각으로 자르면 예전 지진이 나중에 고쳐진 경우를 놓칩니다.
증분은 "안 바뀐 묶음은 그대로 둔다"는 가정에 기대므로, 원본에서 지진이 빠지면 옛 값이 남습니다. 그래서 매 실행마다 집계 합계를 원본과 대조하는 테스트를 두었고, 어긋나면 `--full-refresh` 로 다시 만듭니다.

**dbt 를 돌리기 전에 원본부터 본다.** 파일이 없거나 약속한 열이 빠지면(`check_sources`) 모델을 만들기 전에 멈추고, 그 실패도 실행 기록에 남깁니다.

## 채용 공고 (Remote OK · Arbeitnow)

매일 두 공개 피드에서 공고를 받아 `data/jobs.csv` 에 합치고, 기술별 언급 비중을 주 단위로 집계합니다.

```
jobs.csv ─ stg_jobs ─ int_job_skills ─┬─ dim_skill ─ fct_skill_demand_weekly
skills (사전, seed) ──────────────────┘  fct_job_postings ─ fct_jobs_daily
jobs_fetch_log.csv ─ stg_jobs_fetch_log
```

**본문은 저장하지 않고, 받는 순간 기술 이름만 뽑는다.** 공고 본문을 저장소에 쌓지 않으려고, 수집할 때 기술 사전(`seeds/skills.csv`, 50개)으로 제목과 본문을 훑어 이름 목록만 남깁니다.
대가는 분명합니다. 사전을 고쳐도 예전 공고는 다시 훑을 수 없습니다. 그래서 어느 판의 사전으로 뽑았는지(`skills_dict`)를 행마다 적어 둡니다.

**Remote OK 의 태그는 쓰지 않는다.** 처음 받은 98건 가운데 `golang` 태그가 29건이었는데 제목에 Go 가 나오는 공고는 0건이었습니다(간호사·채용 담당자 공고에도 붙어 있음). 태그 대신 제목·본문에서 직접 찾습니다.

**급여 단위는 추측해 고치지 않는다.** 급여 칸에 시급(21), 월급(4000), 천 단위 생략(110~130), 센트로 보이는 값(114000000)이 섞여 있었습니다.
연봉으로 볼 수 있는 범위(1만~100만 달러)만 쓰고 나머지는 `salary_quality` 에 `suspect_*` 로 표시만 합니다. 처음 받은 자료에서는 급여가 있는 29건 중 23건만 쓸 수 있었습니다.

**수집 구간이 이어졌는지 기록한다.** 두 피드 모두 "최근 N건"만 주므로, 이미 아는 공고가 나올 때까지 쪽을 넘깁니다(최대 8쪽).
끝까지 아는 공고가 안 나오면 그 사이 공고를 놓친 것이므로 수집 기록에 `overlap = no` 로 남고, dbt 가 경고합니다. 지나간 공고는 다시 받을 수 없어서, 고치는 대신 사실을 남깁니다.

**글자가 깨진 제목을 되돌린다.** Remote OK 제목 일부가 `â\x80\x94` 처럼 깨져 왔습니다(UTF-8 이 Latin-1 로 한 번 더 풀린 것). 되돌릴 수 있을 때만 되돌립니다.

한계
- 해외 원격·유럽(독일어권 중심) 공고입니다. 국내 채용 시장을 말해 주지 않습니다.
- 사전에 있는 이름이 글에 나왔는지만 봅니다. "우대"인지 "필수"인지, 얼마나 깊이 요구하는지는 알 수 없습니다. 본문에 흔히 쓰이는 낱말(AI 등)은 실제보다 많이 잡힐 수 있습니다.
- 공고가 피드에서 사라진 것이 마감을 뜻하지는 않습니다(최근 N건 창에서 밀려난 것일 수 있음). 그래서 마감까지 걸린 기간은 계산하지 않습니다.
- 이제 막 모으기 시작했습니다. 주별 추세는 몇 주 쌓인 뒤에야 의미가 있습니다.

출처: [Remote OK](https://remoteok.com) · [Arbeitnow](https://www.arbeitnow.com) 공개 피드 (각 서비스의 이용 조건에 따라 출처를 밝히고 원문 링크를 보존합니다).

## 품질 테스트 (58개)

- 열 단위: `unique` · `not_null` · `relationships`(사실 표의 날짜·지역이 차원에 있는가) · `accepted_values` · 직접 만든 `accepted_range`(규모 0~10, 위도·경도, 수요 20~120 GW 등)
- 표 단위(`tests/*.sql`): 하루는 정확히 24행 · 이웃 행 간격은 항상 1시간 · 일 요약의 최대값이 시간 표에서 다시 계산한 값과 같은가
- 증분 모델 대조: 월별 집계의 합계·최대 규모가 원본에서 다시 센 값과 같은가 · (월, 지역)이 한 줄인가
- 경고: 지진 목록이 14일 넘게 갱신되지 않으면 실패가 아닌 경고(`warn_quakes_stale`)

## 실행

```bash
pip install -r requirements.txt
dbt build --profiles-dir .                        # 모델 + 테스트 + 변경 이력
python -m wh.cli run --date 2026-11-13            # 원본 확인 → dbt build → 파티션 내보내기 → 실행 기록
python -m wh.cli backfill 2025-03-01 2025-03-07   # 과거 날짜 다시 채우기
python -m wh.cli report                           # docs/index.html
python -m wh.cli collect-jobs                     # 채용 공고 피드 수집
python -m pytest -q                               # 26개
```

Airflow (Docker 없이 확인하는 방법 — dbt 와 의존성이 부딪히지 않게 가상환경을 나눕니다):

```bash
python -m venv .dbt && .dbt/bin/pip install dbt-duckdb
pip install "apache-airflow>=3,<4" duckdb
export AIRFLOW_HOME=$PWD/airflow_home AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags AIRFLOW__CORE__LOAD_EXAMPLES=False DBT_BIN=$PWD/.dbt/bin/dbt
airflow db migrate
airflow dags test warehouse_daily 2026-11-13
```

DAG `warehouse_daily`: `collect_jobs → check_sources → dbt_build → export_partition → record → report`.
원본 확인과 dbt 는 2번까지 재시도하고, `record`·`report` 는 앞 단계가 실패해도 실행됩니다(`trigger_rule="all_done"`).
작업은 얇은 껍데기이고 실제 일은 `wh/pipeline.py` 의 함수가 하므로, 명령줄·테스트·Airflow 가 같은 코드를 씁니다.

## 테스트가 확인하는 것 (`pytests/`)

가짜 원본 3일치를 만들어 dbt 프로젝트를 끝까지 돌립니다.
- `24시` 행이 그날 23:00 에 남는지, 일 요약 값이 손으로 계산한 값과 같은지
- 중복 지진 ID · 범위를 벗어난 규모 · 빈 시간 칸을 넣으면 **빌드가 실패하는지**
- 규모가 4.5 → 4.8 로 고쳐지면 이력이 두 판이 되고, 다시 돌려도 판이 늘지 않으며, 과거 시점 값을 되물을 수 있는지
- 증분으로 이어 쌓은 월별 집계가 처음부터 다시 만든 결과와 같은지, 원본에서 지진이 빠지면 대조 테스트가 잡는지
- 빈 DB 에서 시작해도 저장해 둔 이력에서 이어 쌓이는지
- 내보내기가 멱등인지, 자료에 없는 날짜는 빈 폴더를 만들지 않는지, 날짜가 아닌 입력을 거절하는지

## 한계

- **자료가 작습니다.** 지진 약 2,500건, 수요 8,760행이라 성능·비용 이야기는 할 수 없고, 구조와 품질 관리만 보여 줍니다.
- **수요 자료가 2025년 한 해뿐입니다.** 매일 실행에서는 실행 날짜의 월·일을 2025년으로 옮겨 그 파티션을 다시 내보내 재실행 안전성만 확인합니다. 새 수요가 들어오는 진짜 증분 적재는 아닙니다.
- **Airflow 는 `airflow dags test` 로 한 번 실행되는 것만 확인했습니다.** 스케줄러를 며칠 띄워 둔 운영 경험은 아닙니다. 매일 실행은 GitHub Actions 가 같은 함수를 불러 합니다.
- **증분 경로는 테스트에서만 돕니다.** 매일 실행(CI)은 빈 DB 에서 시작하므로 `fct_quakes_monthly` 가 매번 전체로 만들어집니다. 증분 동작은 pytest 가 확인합니다.
- **클라우드 웨어하우스(BigQuery 등)로는 아직 옮기지 않았습니다.** DuckDB 파일 하나로 돕니다.
- 변경 이력은 이 프로젝트를 시작한 날부터 쌓입니다. 그 전에 고쳐진 값은 알 수 없습니다.

데이터 출처: USGS FDSN(공공), 전력거래소 시간별 수요(공공데이터포털), Open-Meteo(CC BY 4.0) — 각 원본 프로젝트 README 참고.
