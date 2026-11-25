# public-data-mcp — AI 가 공공데이터포털 API 를 안전하게 부르게 하는 MCP 서버

Claude 같은 AI 에이전트가 **공공데이터포털(data.go.kr) API** 를 도구 호출(MCP)로 직접 찾고 부르게 합니다.
응급실·대기질·날씨 같은 공공 API 를 붙일 때마다 반복되는 일(인증키 다루기, 오류 코드 해석, 페이지 넘김, 같은 요청 줄이기)을 서버가 맡습니다.

er-access 를 만들며 겪은 불편에서 시작했습니다: 인증키가 URL 에 들어가 로그에 새기 쉽고, 오류는 `30` 같은 숫자로만 오고,
실시간 자료는 같은 요청을 짧은 간격으로 되풀이하게 됩니다.

## 도구 4개

| 도구 | 하는 일 |
|---|---|
| `list_apis(query)` | 등록된 API 목록 (제목·제공 기관으로 거르기) |
| `describe_api(api_id)` | 인자(필수 여부·설명), 응답 형식, 캐시 시간, 활용 신청 페이지, 명세 확인 여부 |
| `call_api(api_id, params, max_rows)` | 호출해 항목을 돌려줌 — 페이지를 넘겨 모으고(최대 1000행), 같은 인자는 캐시에서 |
| `cache_status()` | 캐시 항목 수, 가장 오래된 항목 나이 |

## 지키는 것

| 위험 | 막는 방법 (`pubdata/client.py`) |
|---|---|
| AI 가 아무 주소나 부름 | `registry.yaml` 에 등록된 API·인자만. 등록부의 주소도 `apis.data.go.kr`·`api.odcloud.kr` 만 허용 |
| 인증키가 새어 나감 | 키는 환경변수 `DATA_GO_KR_KEY` 로만. 돌려주는 값·오류·캐시 키 어디에도 없음 (네트워크 오류 메시지 속 URL 까지 가림). 인자로 `serviceKey` 를 몰래 넣는 것도 거부 |
| 오류가 숫자로만 옴 | 공공데이터포털 공통 오류 코드 17종을 원인·해결로 바꿈 (일반 응답과 게이트웨이 응답 두 형식) |
| 같은 요청 반복 · 호출 한도 | API 마다 캐시 시간(실시간 병상 5분, 기관 목록 1일, 공휴일 1주) |
| 너무 큰 응답 | `max_rows` 최대 1000, 전체 건수보다 적게 받으면 `truncated: true` |

## 등록된 API (6개)

응급의료기관 목록 · 응급실 실시간 가용 병상 (국립중앙의료원) · 시도별 실시간 대기오염 (에어코리아) · 단기예보 · 초단기실황 (기상청) · 공휴일 (한국천문연구원)

> **명세는 아직 실제 호출로 확인하지 않았습니다.** 이 서버를 만든 환경(해외 IP)에서는 공공데이터포털에 연결되지 않습니다.
> 그래서 모든 API 에 `verified: false` 를 달고, 응답 항목은 받은 이름 그대로 돌려줍니다. 한국에서 처음 불러 보고 응답 위치나
> 인자 이름이 다르면 `registry.yaml` 만 고치면 됩니다. API 를 더하는 것도 이 파일에 한 덩어리를 추가하면 끝입니다.

## 실행

```bash
pip install -r requirements.txt
python -m pytest -q                      # 12 passed — 인자 검사, 키 가리기, 오류 두 형식, 페이지·캐시, stdio MCP 왕복
DATA_GO_KR_KEY=발급받은키 python -m pubdata.server
```

MCP 클라이언트(Claude Code 등)에 붙이려면 `.mcp.json` 에:

```json
{
  "mcpServers": {
    "public-data": { "command": "python", "args": ["-m", "pubdata.server"], "cwd": "public-data-mcp",
                     "env": { "DATA_GO_KR_KEY": "발급받은 일반 인증키(Decoding)" } }
  }
}
```

환경변수: `DATA_GO_KR_KEY`(필수), `PUBDATA_CACHE`(캐시 파일, 기본 `~/.cache/pubdata-mcp/cache.sqlite`), `PUBDATA_REGISTRY`(다른 등록부).
