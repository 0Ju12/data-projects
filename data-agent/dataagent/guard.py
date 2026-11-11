"""LLM 이 만든 SQL 을 그대로 믿지 않기 위한 안전장치 — 읽기만, 한 문장만, 정해진 양만.

세 겹으로 막습니다.
1. 문장 검사: 주석을 지운 뒤 SELECT / WITH 로 시작하는 한 문장인지
2. 연결: SQLite 를 읽기 전용(mode=ro)으로 열기
3. 실행 권한: authorizer 로 SELECT·열 읽기·함수 호출만 허용 (ATTACH, PRAGMA, 쓰기, load_extension 거부)
그리고 행 수와 실행 시간을 제한합니다.
"""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

MAX_ROWS = 200
TIMEOUT_S = 3.0


class SQLRejected(ValueError):
    pass


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def check_statement(sql: str) -> str:
    s = strip_comments(sql).strip().rstrip(";").strip()
    if not s:
        raise SQLRejected("빈 SQL 입니다.")
    if ";" in re.sub(r"'(?:[^']|'')*'", "''", s):
        raise SQLRejected("한 번에 한 문장만 실행할 수 있습니다.")
    if not re.match(r"(?is)^(select|with)\b", s):
        raise SQLRejected("SELECT (또는 WITH … SELECT) 만 실행할 수 있습니다.")
    return s


def _authorizer(action, arg1, arg2, dbname, source):
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_DENY if (arg2 or "").lower() == "load_extension" else sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def run(db: Path, sql: str, max_rows: int = MAX_ROWS, timeout_s: float = TIMEOUT_S) -> dict:
    """{"columns": [...], "rows": [[...]], "row_count": n, "truncated": bool}"""
    stmt = check_statement(sql)
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        con.set_authorizer(_authorizer)
        t0 = time.monotonic()
        con.set_progress_handler(lambda: 1 if time.monotonic() - t0 > timeout_s else 0, 10_000)
        try:
            cur = con.execute(stmt)
            rows = cur.fetchmany(max_rows + 1)
        except sqlite3.DatabaseError as e:
            msg = str(e)
            if "not authorized" in msg or "prohibited" in msg:
                raise SQLRejected("읽기 전용입니다. 허용되지 않은 동작이 들어 있습니다.") from e
            if "interrupted" in msg:
                raise SQLRejected(f"실행 시간이 {timeout_s:g}초를 넘어 중단했습니다. 범위를 좁혀 주세요.") from e
            raise SQLRejected(f"SQL 오류: {msg}") from e
        cols = [d[0] for d in cur.description or []]
        return {"columns": cols, "rows": [list(r) for r in rows[:max_rows]], "row_count": min(len(rows), max_rows), "truncated": len(rows) > max_rows}
    finally:
        con.close()
