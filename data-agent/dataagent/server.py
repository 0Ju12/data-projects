"""MCP 서버 (stdio).  실행:  python -m dataagent.server

도구
- list_tables()                        어떤 표가 있는지
- describe_table(name)                 열 설명과 예시 3행
- run_sql(sql)                         읽기 전용 SELECT 실행 (최대 200행, 3초)
- check_answer(question, sql, answer)  SQL 을 다시 실행해, 답 속 숫자가 결과에 근거가 있는지 확인
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import build_db, guard, verify

DB = Path(os.environ.get("DATAAGENT_DB", build_db.DB))
mcp = FastMCP("data-projects")


def _ensure_db() -> None:
    if not DB.exists():
        build_db.build(DB)


@mcp.tool()
def list_tables() -> list[dict]:
    """조회할 수 있는 표와 설명, 행 수를 돌려줍니다. 처음에 한 번 불러 무엇이 있는지 확인하세요."""
    _ensure_db()
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return [{"table": t, "description": d, "rows": con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]}
                for t, d in con.execute("SELECT table_name, description FROM _catalog WHERE column_name = ''")]
    finally:
        con.close()


@mcp.tool()
def describe_table(name: str) -> dict:
    """표의 열 설명과 예시 3행을 돌려줍니다. SQL 을 쓰기 전에 열 이름과 값의 형식을 확인하세요."""
    _ensure_db()
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        cols = con.execute("SELECT column_name, description FROM _catalog WHERE table_name = ? AND column_name != ''", (name,)).fetchall()
        if not cols:
            return {"error": f"'{name}' 표가 없습니다. list_tables 로 이름을 확인하세요."}
        sample = guard.run(DB, f'SELECT * FROM "{name}" LIMIT 3')
        return {"table": name, "columns": [{"name": c, "description": d} for c, d in cols], "sample": sample}
    finally:
        con.close()


@mcp.tool()
def run_sql(sql: str) -> dict:
    """읽기 전용 SQL(SELECT 한 문장)을 실행합니다. 최대 200행, 3초. 합계·평균·차이는 SQL 안에서 계산해 결과에 넣으세요."""
    _ensure_db()
    try:
        return guard.run(DB, sql)
    except guard.SQLRejected as e:
        return {"error": str(e)}


@mcp.tool()
def check_answer(question: str, sql: str, answer: str) -> dict:
    """사용자에게 답하기 전에 부르세요. sql 을 다시 실행해 answer 에 적힌 숫자가 모두 조회 결과에 근거가 있는지 확인합니다.
    unsupported 에 숫자가 있으면 답을 고치거나, 그 값을 계산하는 SQL 로 다시 조회하세요."""
    _ensure_db()
    try:
        result = guard.run(DB, sql)
    except guard.SQLRejected as e:
        return {"ok": False, "error": str(e)}
    out = verify.check(answer, result, question)
    out["row_count"] = result["row_count"]
    return out


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
