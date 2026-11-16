# API Watch — 데이터 신뢰도 관제 + 하루 한 개 AI 학습

[온라인 관제판](https://0ju12.github.io/data-projects/api-watch/) · [정기/수동 실행](https://github.com/0Ju12/data-projects/actions/workflows/api-watch.yml)

HTTP 200이어도 오래된 자료·빈 결과·중복·자료형 변경을 별도로 검사합니다. 실제 HTTP 검사, 합성 장애 실험, 개인 AI 학습 노트를 구분합니다.

## 첫 검사 대상

| 대상 | 검사 | 최신성 기준 |
|---|---|---|
| USGS 전 세계 최근 24시간 지진 | 필수 필드·ID 중복·건수·구조 | 피드 생성 시각 20분 |
| Open-Meteo 서울 현재 날씨 | 필수 필드·온도·습도·풍속 범위·구조 | 자료 시각 90분 |
| 본인 지진 파이프라인 summary.json | 결과 필드·지역 ID·일일 산출물 | 생산 코드의 UTC 갱신 시각 36시간 |

인증키 없는 공개 주소만 사용합니다. 지역에서 지진이 없다는 사실과 API 오류는 다르므로 다른 범위를 추가할 때는 최소 건수를 직접 결정하세요. `quality.mag_types`처럼 항목이 변하는 범주 사전은 고정 구조 비교에서 제외합니다.

## 운영과 지표

- 시간당 검사하며, GitHub 스케줄 지연·비활성화에 대비해 관제 보고서 자체가 150분 이상 오래됐는지도 표시합니다.
- 응답 실패는 첫 회 주의, 연속 두 회부터 이상 감지입니다. 품질 위반은 HTTP 성공과 별개입니다.
- 같은 실패는 열린 이슈 한 건으로 모읍니다. 실제로 관측해 통과한 검사만 회복 처리하며 네트워크 실패 중의 데이터 품질을 정상으로 바꾸지 않습니다.
- 첫 정상 응답의 구조를 저장하고 실패한 응답으로 자동 교체하지 않습니다. 새 필드 추가와 자료형 변경·필드 삭제를 구분합니다.
- 성공률은 관측한 검사 표본의 비율이지 가동률/SLA가 아닙니다. p95는 표본 5회 이상부터 표시합니다.
- 응답 전체 대신 검사 근거·구조·개수·시각만 저장합니다. 실제 upstream 장애는 기록하고 보고서 배포를 계속하며, 엔진·설정·저장 자체의 오류는 작업 실패입니다.
- 온라인 GitHub 배포판은 조회용입니다. 수동 실행 버튼은 실제 Actions 화면으로 이동합니다. Django 실행판의 `/api/run`은 관리자 로그인과 CSRF 검증 후 직접 검사합니다.

## 하루 한 개 AI 노트

한국 날짜 기준 하루 한 건을 유지합니다. Transformers, vLLM, Ollama, llama.cpp, LangGraph 공식 안정 릴리스와 선택한 공개 모델 조직의 Hugging Face 메타데이터를 봅니다. 최근 30일의 미소개 항목 중 하나를 고르며 AI 생태계 전체의 최신 순위가 아닙니다.

기술 설명·개념 흐름·본인의 RAG/VQA/모델 실험과 연결할 점·짧은 실습·한계·원문을 제공합니다. 발표일·모델 저장소 수정일·수집일을 구분합니다. 새 자료를 확인하지 못하면 기존 기술 학습으로 표시합니다. 모델 가중치 다운로드·실행은 하지 않습니다.

공식 메타데이터와 사전 작성한 한국어 설명을 조합한 첫 버전이며, LLM이 내용을 검증하거나 모델 성능을 비교한 결과가 아닙니다. 개인 학습 메모는 브라우저에만 저장합니다. 메시지·이메일 자동 발송은 없습니다.

## 로컬 실행 (SQLite)

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py monitor
python manage.py createsuperuser
python manage.py runserver
```

`http://127.0.0.1:8000/`에서 확인합니다. 실제 검사에는 인터넷 연결이 필요합니다. 아래 테스트는 외부 API를 호출하지 않습니다.

```sh
python manage.py test tests
python manage.py check
```

## PostgreSQL + Docker Compose

```sh
cp .env.example .env
# POSTGRES_PASSWORD와 DJANGO_SECRET_KEY를 서로 다른 임의 문자열로 채우세요.
# 생성 예: python -c 'import secrets; print(secrets.token_urlsafe(48))'
docker compose up --build -d
docker compose exec app python manage.py createsuperuser
```

앱의 마이그레이션·정적 파일 준비 후 스케줄러가 시작됩니다. DB는 명명된 볼륨에 보관하고 포트는 기본적으로 로컬 주소에 엽니다. 외부 운영 시 HTTPS·허용 호스트·쿠키 보안을 설정하고 실제 비밀값은 커밋하지 마세요. 현재 온라인 인스턴스는 Actions의 SQLite 검사와 Pages 보고서이며, 관리형 PostgreSQL을 별도로 배포했다고 주장하지 않습니다.

## 규칙과 구조 승인

대상별 규칙은 `watchtower/registry.py`에 있습니다. 관리자 화면의 원본 규칙은 읽기 전용입니다. 원문과 구조 변경을 검토한 뒤에만 승인합니다.

```sh
python manage.py accept_schema usgs --confirm
```

타임아웃 12초, 응답 크기·깊이·필드 수 제한을 둡니다. 누락한 값을 임의의 정상 값으로 채우지 않습니다.

## 이력과 재현

- `public/report.json`: 실제 검사, 이력, 이슈, 일일 학습 노트
- `public/lab.json`: 실제 검사 엔진에 합성 장애 10종을 넣은 사전 실행 결과
- `state/checkpoint.json`: CI에서 구조 기준·실패 횟수·이력·이슈·일일 노트를 복원하는 공개 체크포인트

대상별 최근 72회, 이슈 200개, 학습 노트 90개를 보고서에 포함합니다. 상시 서버는 DB를 사용하고 일회성 CI DB는 체크포인트에서 복원합니다. 검사 사이의 관측하지 않은 장애까지 탐지했다고 주장하지 않습니다.

데이터와 모델의 이용 조건은 제공자 문서를 따릅니다. USGS/Open-Meteo/본인 저장소 출처를 상세 화면에 표시합니다. Open-Meteo 출처와 비상업 공개 API의 조건, 각 모델 카드의 라이선스를 별도로 확인하세요.
