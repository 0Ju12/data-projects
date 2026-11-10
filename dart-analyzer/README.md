# dart-analyzer — 전자공시(DART) 데이터 마트와 근거 검색

금융감독원 OpenDART API 로 관심 기업의 **재무 지표와 사업보고서 원문**을 모아 SQLite 데이터 마트로 만들고,
SQL 뷰로 지표를 계산하고, 사업보고서 문단을 **출처와 함께** 찾아 주는 도구입니다. 답을 생성하지 않고 원문 문단을 그대로 보여 줍니다.

지원 회사 분석(사업 부문·매출 구조·수익성)을 매번 손으로 하지 않으려고 만들었고, 금융권 데이터 직무에서 쓰는 SQL 모델링을 직접 연습하는 목적도 있습니다.

## 흐름

```
OpenDART API ─┬ corpCode.xml        회사명 → 고유번호 (상장사 우선, 못 찾으면 건너뛰고 알림)
              ├ fnlttSinglAcnt.json 주요 계정 (연결 CFS 우선, 없으면 별도 OFS) → financials
              ├ list.json           정기공시 목록 → filings
              └ document.xml        사업보고서 원문 → 절·문단 → paragraphs
                                     │
SQLite 마트 ── v_metrics (피벗·영업이익률·부채비율) ── v_growth (LAG 로 전년 대비) ── v_sector_rank (RANK)
                                     │
               ask "회사" "질문"  →  글자 2-gram BM25 → 상위 문단 + 보고서·절·DART 링크 (기준 점수 미만이면 '근거 없음')
```

## SQL (`sql/schema.sql`)

```sql
-- 전년 대비 증가율: 윈도 함수
SELECT corp_name, bsns_year, revenue,
       ROUND(100.0 * (revenue - LAG(revenue) OVER w) / NULLIF(ABS(LAG(revenue) OVER w), 0), 2) AS revenue_yoy_pct
FROM v_metrics WINDOW w AS (PARTITION BY corp_code ORDER BY bsns_year);
```

- 계정명이 회사마다 달라(매출액·수익(매출액)·영업수익 …) 표준 계정으로 묶은 뒤 피벗합니다.
- 0 으로 나누기는 `NULLIF`, 적자 전환 기업의 증감률은 분모에 `ABS` 를 써서 부호가 뒤집히지 않게 했습니다.

## 설계 판단

- **키 관리**: 인증키는 환경변수 `DART_API_KEY`(GitHub Actions 에서는 Secrets)로만 받습니다. 코드·로그·저장소에 남기지 않습니다.
- **오류 구분**: DART 응답 `013`(데이터 없음)은 빈 결과, `020`(요청 한도)은 대기 후 재시도, 그 밖은 예외. 원문 ZIP 대신 오류 메시지가 오면 그대로 보여 줍니다.
- **검색 방식**: 한국어 공시 문장은 조사·복합어 때문에 단어 단위 일치가 잘 안 돼 글자 2-gram BM25 를 썼습니다. 생성형 답변 대신 원문 문단과 출처를 돌려주고, 관련 문단이 없으면 "근거 없음"을 돌려줍니다 (국보 RAG 가이드의 근거 검증 원칙과 같은 방향).
- **원문 파싱**: DART 원문은 HTML 에 가까운 XML 이라 엄격한 파서가 실패하면 태그를 걷어 내는 방식으로 대체합니다.

## 실행

```bash
export DART_API_KEY=...            # https://opendart.fss.or.kr 에서 무료 발급
python -m dartmart.pipeline build  # config.json 의 회사·연도 수집 → data/dart.sqlite, reports/metrics.md
python -m dartmart.pipeline report
python -m dartmart.pipeline ask "포스코인터내셔널" "LNG 사업 투자 계획"
python -m pytest -q                # 테스트 14개 — 가상 데이터와 가짜 클라이언트로, 실제 DART 에 접속하지 않음
```

GitHub Actions(저장소 루트 `.github/workflows`): `tests`(푸시마다), `dart build mart`(수동 실행 또는 매월 1일, 저장소 Secrets 에 `DART_API_KEY` 가 있어야 함).

## 상태

- 수집·마트·검색 코드와 테스트는 완성. **실제 수집 결과(`reports/metrics.md`)는 인증키를 넣고 처음 실행하면 생성됩니다.**
- `tests/fixtures` 의 회사(예시전자·예시에너지)와 수치는 테스트용 가상 데이터입니다.
- 다음 단계: 사업 부문별 매출(주석 표) 파싱, 지원 회사 비교 대시보드.
