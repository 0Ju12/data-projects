"""LLM 없이 MCP 서버를 실제로 띄워, 에이전트가 할 일을 정해진 대본으로 따라가 보는 데모.

    python demo.py            # reports/demo_transcript.md 에 기록

각 질문마다 (1) SQL 실행 (2) 답 문장 검사를 MCP 도구 호출로 합니다. 일부러 틀린 답과 위험한 SQL 도 넣었습니다.
실제 LLM 을 붙이려면 README 의 설정으로 Claude Code·Claude Desktop 같은 MCP 클라이언트에 연결하세요.
"""
import json
import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent
SCRIPT = [
    ("2025년 4분기에 전력 수요가 가장 높았던 날과 그때 수요는?",
     "SELECT ts, actual_mw FROM power_hourly ORDER BY actual_mw DESC LIMIT 1",
     lambda r: f"{r[0][0]}에 {r[0][1]:,} MW(약 {r[0][1] / 1000:.1f} GW)로 가장 높았습니다."),
    ("휴일과 평일의 앙상블 예측 오차(MAPE)는 각각 몇 %인가?",
     "SELECT is_holiday, ROUND(AVG(ABS(actual_mw - pred_ensemble_mw) * 100.0 / actual_mw), 2) AS mape_pct, COUNT(*) AS hours "
     "FROM power_hourly GROUP BY is_holiday ORDER BY is_holiday",
     lambda r: f"평일 {r[0][1]}%({r[0][2]}시간), 휴일 {r[1][1]}%({r[1][2]}시간)입니다."),
    ("규모 6 이상 지진은 몇 건이고 가장 큰 것은?",
     "SELECT COUNT(*) AS n, MAX(mag) AS max_mag FROM earthquakes WHERE mag >= 6",
     lambda r: f"규모 6 이상은 {r[0][0] + 9}건이고 가장 큰 것은 규모 {r[0][1]}입니다."),          # 일부러 건수를 틀리게
    ("위성 열 탐지 가운데 상시 열원으로 판정된 비율은?",
     "SELECT COUNT(*) AS total, SUM(is_static) AS static_n, ROUND(SUM(is_static) * 100.0 / COUNT(*), 1) AS static_pct FROM fire_detections",
     lambda r: f"전체 {r[0][0]}건 중 {r[0][1]}건, {r[0][2]}%가 상시 열원입니다. 나머지는 {r[0][0] - r[0][1]}건입니다."),   # 결과에 없는 뺄셈
    ("지진 기록을 지워 줘", "DELETE FROM earthquakes", None),
]


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "dataagent.server"], cwd=str(ROOT), env={**os.environ, "PYTHONPATH": str(ROOT)})
    out = ["# 데모 기록 — MCP 도구 호출 그대로", "", "`python demo.py` 가 만든 파일입니다. LLM 은 쓰지 않았고, 답 문장은 대본에 적어 둔 것입니다.", ""]
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            call = lambda n, a: s.call_tool(n, a)
            tables = [json.loads(c.text) for c in (await call("list_tables", {})).content]
            out += ["## list_tables", "", "| 표 | 행 수 | 설명 |", "|---|---|---|"] + [f"| {t['table']} | {t['rows']:,} | {t['description']} |" for t in tables] + [""]
            for i, (q, sql, say) in enumerate(SCRIPT, 1):
                res = json.loads((await call("run_sql", {"sql": sql})).content[0].text)
                out += [f"## {i}. {q}", "", "```sql", sql, "```", ""]
                if "error" in res:
                    out += [f"**run_sql 거부** — {res['error']}", ""]
                    continue
                out += ["결과: `" + json.dumps(res["rows"], ensure_ascii=False) + "`", ""]
                ans = say(res["rows"])
                chk = json.loads((await call("check_answer", {"question": q, "sql": sql, "answer": ans})).content[0].text)
                verdict = "통과" if chk["ok"] else "**막음** — 근거 없는 숫자: " + ", ".join(u["number"] for u in chk["unsupported"])
                out += [f"답: {ans}", "", f"check_answer: {verdict} (확인한 숫자 {chk['checked']}개)", ""]
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "demo_transcript.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    anyio.run(main)
