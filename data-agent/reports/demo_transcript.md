# 데모 기록 — MCP 도구 호출 그대로

`python demo.py` 가 만든 파일입니다. LLM 은 쓰지 않았고, 답 문장은 대본에 적어 둔 것입니다.

## list_tables

| 표 | 행 수 | 설명 |
|---|---|---|
| earthquakes | 2,476 | USGS 지진 목록 (동아시아, 규모 4 이상). geo-data-pipeline 이 매일 갱신. |
| power_hourly | 2,208 | 2025-10-01 ~ 12-31 전국 시간별 전력 수요와 하루 전 예측 (시험 구간). power-demand 결과. |
| fire_detections | 394 | NASA FIRMS VIIRS 열 탐지 (한국 범위). wildfire-watch 가 매일 갱신. |
| fire_weather | 1,989 | 0.25° 육지 칸별 일 기상과 화재기상지수(FFWI). wildfire-watch 결과. |

## 1. 2025년 4분기에 전력 수요가 가장 높았던 날과 그때 수요는?

```sql
SELECT ts, actual_mw FROM power_hourly ORDER BY actual_mw DESC LIMIT 1
```

결과: `[["2025-12-23 09:00", 82812]]`

답: 2025-12-23 09:00에 82,812 MW(약 82.8 GW)로 가장 높았습니다.

check_answer: 통과 (확인한 숫자 7개)

## 2. 휴일과 평일의 앙상블 예측 오차(MAPE)는 각각 몇 %인가?

```sql
SELECT is_holiday, ROUND(AVG(ABS(actual_mw - pred_ensemble_mw) * 100.0 / actual_mw), 2) AS mape_pct, COUNT(*) AS hours FROM power_hourly GROUP BY is_holiday ORDER BY is_holiday
```

결과: `[[0, 3.05, 2040], [1, 5.38, 168]]`

답: 평일 3.05%(2040시간), 휴일 5.38%(168시간)입니다.

check_answer: 통과 (확인한 숫자 4개)

## 3. 규모 6 이상 지진은 몇 건이고 가장 큰 것은?

```sql
SELECT COUNT(*) AS n, MAX(mag) AS max_mag FROM earthquakes WHERE mag >= 6
```

결과: `[[27, 7.6]]`

답: 규모 6 이상은 36건이고 가장 큰 것은 규모 7.6입니다.

check_answer: **막음** — 근거 없는 숫자: 36 (확인한 숫자 3개)

## 4. 위성 열 탐지 가운데 상시 열원으로 판정된 비율은?

```sql
SELECT COUNT(*) AS total, SUM(is_static) AS static_n, ROUND(SUM(is_static) * 100.0 / COUNT(*), 1) AS static_pct FROM fire_detections
```

결과: `[[394, 356, 90.4]]`

답: 전체 394건 중 356건, 90.4%가 상시 열원입니다. 나머지는 38건입니다.

check_answer: **막음** — 근거 없는 숫자: 38 (확인한 숫자 4개)

## 5. 지진 기록을 지워 줘

```sql
DELETE FROM earthquakes
```

**run_sql 거부** — SELECT (또는 WITH … SELECT) 만 실행할 수 있습니다.
