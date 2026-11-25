# pipeline-status — 데이터 파이프라인 상태판과 실패 알림

이 저장소는 GitHub Actions 로 매일·매시간 자료를 모읍니다. 지진, 산불, 웨어하우스, 공고, 전력 전환, API Watch 가 그렇습니다.
워크플로가 초록색이어도 자료가 멈춰 있을 수 있어서, 세 가지를 함께 보는 상태판을 만들었습니다.

[파이프라인 상태판](https://0ju12.github.io/data-projects/status/) · 매일 배포 때 갱신, 페이지에서 실행 기록만 실시간으로 다시 받기 가능

| 보는 것 | 어떻게 |
|---|---|
| 워크플로 실행 기록 | main 의 최근 30번: 성공률, 걸린 시간 중앙값, 연속 실패, 마지막 성공 (GitHub Actions REST API) |
| 숨은 실패 | 아래 설명 |
| 산출물 신선도 | 프로젝트마다 남기는 갱신 시각을 읽어 기준 시간과 비교 ([sources.json](status/sources.json)). 웨어하우스 실행 기록의 `status`·`tests_fail` 과 산불 출처별 받은 건수도 확인 |

## 숨은 실패

매일 갱신 워크플로(`geo daily update`)는 산불·웨어하우스·공고·전력 단계에 `continue-on-error: true` 를 씁니다. 한 출처가 막혀도 지진 갱신과 배포는 계속하기 위해서입니다.
대신 그 단계가 실패해도 **작업은 성공으로 끝나고, API 의 단계 결과(conclusion)도 success 로 바뀝니다**. 실제 실행 기록을 열어 보고 확인한 점입니다.
그래서 두 길로 찾습니다.

1. 워크플로 안에서 실행할 때 `STEP_OUTCOMES: ${{ toJSON(steps) }}` 로 단계마다 `outcome`(continue-on-error 적용 전 결과)을 받습니다. `outcome=failure` 인데 `conclusion=success` 면 숨은 실패입니다.
2. 밖에서 볼 때는 성공한 작업의 실패 주석(check-run annotation, `Process completed with exit code 1.`)을 읽습니다.

## 알림

`pipeline status` 워크플로가 매일 갱신·테스트가 끝날 때마다, 그리고 6시간마다 점검합니다.

- 빨간 문제(연속 실패, 늦은 산출물, 실패한 점검)가 있으면 `pipeline-alert` 라벨 이슈를 **하나만** 엽니다
- 문제 목록이 바뀔 때만 이슈 본문을 고치고 댓글을 답니다 (본문에 문제 지문 `fp:` 를 숨겨 둠 → 같은 문제로 매번 알림이 오지 않음)
- 빨간 문제가 모두 없어지면 댓글을 남기고 닫습니다. 주황(숨은 실패, 일부 출처 0건)은 이슈 본문에만 적습니다

## 실행

```bash
python -m pytest -q                                     # 7개 (가짜 API 로 실행 요약·숨은 실패·신선도·이슈 열기/고치기/닫기)
python -m status.collect --repo 0Ju12/data-projects     # docs/status.json, GITHUB_TOKEN 이 있으면 사용
python -m status.collect --offline                      # API 없이 신선도만
```

표준 라이브러리만 씁니다. API 를 읽지 못해도 신선도 점검은 내고, 그때는 알림을 건너뜁니다.
