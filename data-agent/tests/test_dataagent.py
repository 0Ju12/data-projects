import json
import os
import sqlite3
import sys
from pathlib import Path

import anyio
import pytest

from dataagent import build_db, guard, verify

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def db(tmp_path_factory):
    p = tmp_path_factory.mktemp("db") / "agent.sqlite"
    counts = build_db.build(p)
    assert counts["power_hourly"] == 92 * 24 and counts["earthquakes"] > 1000 and counts["fire_weather"] > 0
    return p


def test_select_runs_and_limits_rows(db):
    r = guard.run(db, "SELECT date, MAX(actual_mw) AS peak FROM power_hourly GROUP BY date ORDER BY peak DESC LIMIT 2;")
    assert r["columns"] == ["date", "peak"] and r["row_count"] == 2 and not r["truncated"]
    big = guard.run(db, "SELECT * FROM power_hourly")
    assert big["row_count"] == guard.MAX_ROWS and big["truncated"]
    assert guard.run(db, "WITH x AS (SELECT 1 AS a) SELECT a FROM x -- 주석")["rows"] == [[1]]


@pytest.mark.parametrize("sql", [
    "DROP TABLE power_hourly",
    "DELETE FROM earthquakes",
    "UPDATE earthquakes SET mag = 9",
    "INSERT INTO earthquakes(id) VALUES ('x')",
    "SELECT 1; DROP TABLE earthquakes",
    "/* 숨김 */ PRAGMA writable_schema = 1",
    "ATTACH DATABASE '/tmp/x.db' AS x",
    "WITH x AS (SELECT 1) DELETE FROM earthquakes",
    "SELECT load_extension('x')",
    "",
])
def test_everything_but_one_select_is_rejected(db, sql):
    before = sqlite3.connect(db).execute("SELECT COUNT(*), MAX(mag) FROM earthquakes").fetchone()
    with pytest.raises(guard.SQLRejected):
        guard.run(db, sql)
    assert sqlite3.connect(db).execute("SELECT COUNT(*), MAX(mag) FROM earthquakes").fetchone() == before


def test_semicolon_inside_string_is_allowed_and_timeout_stops(db):
    assert guard.run(db, "SELECT 'a;b' AS s")["rows"] == [["a;b"]]
    slow = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"
    with pytest.raises(guard.SQLRejected, match="중단"):
        guard.run(db, slow, timeout_s=0.2)


def test_verify_supported_rounding_units_and_given():
    res = {"columns": ["date", "peak_mw", "mape"], "rows": [["2025-12-26", 87193, 0.03231]], "row_count": 1, "truncated": False}
    ok = verify.check("2025년 4분기 최대 수요는 12월 26일의 87,193 MW(약 87.2 GW)였고 오차는 3.23%입니다.", res, "2025년 4분기 최대 수요는?")
    assert ok["ok"] and ok["checked"] == 7
    basis = {s["number"]: s["basis"] for s in ok["supported"]}
    assert basis["87,193"] == "결과 값" and basis["87.2"] == "결과 값 ÷ 1000" and basis["3.23"] == "결과 값 × 100" and basis["2025"] == "결과 값"


def test_verify_catches_wrong_and_invented_numbers():
    res = {"columns": ["n", "max_mag"], "rows": [[12, 6.3]], "row_count": 1, "truncated": False}
    bad = verify.check("규모 5 이상 지진은 21건이고 가장 큰 것은 규모 6.8입니다.", res, "규모 5 이상 지진은 몇 건?")
    assert not bad["ok"] and [u["number"] for u in bad["unsupported"]] == ["21", "6.8"]      # 자리 바뀜, 지어낸 값
    assert verify.check("12건, 최대 규모 6.3", res, "")["ok"]
    assert not verify.check("12건으로 지난달 8건보다 4건 늘었습니다.", res, "")["ok"]           # 결과에 없는 비교
    assert verify.check("결과는 3건입니다.", {"rows": [["a"], ["b"], ["c"]], "row_count": 3, "truncated": False})["supported"][0]["basis"] == "행 수"


def test_number_extraction():
    assert [n for _, n, _ in verify.numbers("1,234.5 MW, -3.2%, 2025-10-06, v2")] == [1234.5, -3.2, 2025.0, 10.0, 6.0]      # 날짜의 - 는 음수 부호가 아님, v2 의 2 는 숫자로 보지 않음


def test_mcp_server_over_stdio(db):
    """실제 MCP 프로토콜(stdio)로 서버를 띄워 도구를 불러 봄"""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "dataagent.server"], cwd=str(ROOT),
                                       env={**os.environ, "DATAAGENT_DB": str(db), "PYTHONPATH": str(ROOT)})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = sorted(t.name for t in (await s.list_tools()).tools)
                call = lambda n, a: s.call_tool(n, a)
                tables = (await call("list_tables", {})).content
                ok = json.loads((await call("run_sql", {"sql": "SELECT COUNT(*) AS n FROM power_hourly"})).content[0].text)
                rej = json.loads((await call("run_sql", {"sql": "DROP TABLE power_hourly"})).content[0].text)
                chk = json.loads((await call("check_answer", {"question": "몇 시간?", "sql": "SELECT COUNT(*) AS n FROM power_hourly", "answer": "2,280시간입니다."})).content[0].text)
                return names, tables, ok, rej, chk

    names, tables, ok, rej, chk = anyio.run(go)
    assert names == ["check_answer", "describe_table", "list_tables", "run_sql"]
    assert len(tables) >= 1
    assert ok["rows"] == [[2208]] and "error" in rej
    assert chk["ok"] is False and chk["unsupported"] == [{"number": "2,280"}]
