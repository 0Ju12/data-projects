# data-agent — 내 데이터에 묻는 MCP 서버, 답 속 숫자는 코드로 다시 확인

이 저장소의 프로젝트들이 만든 결과(지진 목록, 전력 수요 예측, 산불 탐지·화재기상지수)를 읽기 전용 SQLite 하나로 모으고,
LLM 이 **도구 호출(MCP)** 로 직접 조회하게 하는 서버입니다. LLM 을 믿는 대신 두 군데에서 코드로 막습니다.

| 막는 곳 | 무엇을 | 어떻게 |
|---|---|---|
| **SQL 실행 전** | LLM 이 만든 SQL 이 데이터를 바꾸거나 너무 큰 조회를 하는 것 | SELECT 한 문장만 · 읽기 전용 연결 · SQLite authorizer · 최대 200행 · 3초 (`dataagent/guard.py`) |
| **답을 내기 전** | 조회 결과를 문장으로 옮기며 숫자를 틀리거나 지어내는 것 | 답에서 숫자를 모두 뽑아 조회 결과와 대조 (`dataagent/verify.py`) |

SSAFY 프로젝트에서 한 "LLM 의 판단을 코드로 다시 확인"과 국보 RAG 가이드의 "근거 번호 검증"을, 숫자와 SQL 에 적용한 것입니다.

## 도구 4개

| 도구 | 하는 일 |
|---|---|
| `list_tables()` | 표 목록·설명·행 수 |
| `describe_table(name)` | 열 설명과 예시 3행 |
| `run_sql(sql)` | 읽기 전용 SELECT 실행. 거부하면 이유를 돌려줌 |
| `check_answer(question, sql, answer)` | SQL 을 다시 실행해 답 속 숫자가 근거 있는지 확인 → `unsupported` 목록 |

숫자가 '근거 있음'이 되는 경우는 다섯 가지뿐입니다: 결과 값(답에 적힌 자릿수로 반올림해 비교), 결과 값 ÷ 1000(MW→GW), 결과 값 × 100(비율→%),
행 수, 질문에 이미 나온 값. 답에서 새로 계산한 합계·차이는 근거 없음이 되므로, 그런 값은 SQL 에서 계산해야 통과합니다.

## 실제로 돌려 본 기록

`python demo.py` 는 서버를 stdio 로 띄워 MCP 프로토콜로 도구를 부릅니다 → [reports/demo_transcript.md](reports/demo_transcript.md)

| 질문 | 결과 |
|---|---|
| 4분기 최대 전력 수요 | 통과 — 82,812 MW, "약 82.8 GW"는 ÷1000 으로 확인 |
| 휴일·평일 예측 오차 | 통과 — 3.05% / 5.38% (power-demand 의 results.json 과 같은 값) |
| 규모 6 이상 지진 건수 (답을 27 → 36 으로 틀리게) | **막음** — 36 은 결과에 없음 |
| 상시 열원 비율 (답에서 394 − 356 = 38 을 덧붙임) | **막음** — 38 은 결과에 없는 계산 |
| `DELETE FROM earthquakes` | **run_sql 거부** |

**확인하지 못한 것**: 이 데모의 답 문장은 대본입니다. 실제 LLM 을 붙여 여러 질문을 돌리고 얼마나 자주 막히는지 재는 평가는 하지 않았습니다(API 키 필요).

## 한계

- 숫자만 봅니다. "늘었다 / 가장 높다" 같은 말의 방향이나, 맞는 숫자를 엉뚱한 항목에 붙인 경우는 잡지 못합니다.
- 우연히 같은 숫자가 결과에 있으면 통과합니다(예: 답의 5 와 결과의 다른 열의 5).
- DART 재무 마트는 인증키로 만든 DB 가 저장소에 없어 넣지 않았습니다.

## 실행

```bash
pip install -r requirements.txt
python -m dataagent.build_db      # data/agent.sqlite (형제 폴더의 산출물에서 매번 새로 만듦)
python -m pytest -q               # 16 passed — SQL 거부 10종, 숫자 검증, stdio MCP 왕복
python demo.py
```

MCP 클라이언트(Claude Code 등)에 붙이려면 프로젝트의 `.mcp.json` 에:

```json
{
  "mcpServers": {
    "data-projects": { "command": "python", "args": ["-m", "dataagent.server"], "cwd": "data-agent" }
  }
}
```
