"""MCP 서버 (stdio).  실행:  DATA_GO_KR_KEY=… python -m pubdata.server

도구
- list_apis(query)                     등록된 공공데이터 API 목록 (이름·제공 기관으로 거르기)
- describe_api(api_id)                 인자·응답 위치·캐시 시간·명세 확인 여부
- call_api(api_id, params, max_rows)   호출해 항목을 돌려줌 (페이지 넘김·캐시·오류 설명, 키는 돌려주지 않음)
- cache_status()                       캐시 항목 수와 가장 오래된 항목 나이
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import client

REG = client.load_registry(Path(os.environ.get("PUBDATA_REGISTRY", client.REGISTRY)))
CACHE = client.Cache(Path(os.environ.get("PUBDATA_CACHE", Path.home() / ".cache" / "pubdata-mcp" / "cache.sqlite")))
mcp = MCPServer("public-data")


@mcp.tool()
def list_apis(query: str = "") -> list[dict]:
    """부를 수 있는 공공데이터 API 목록입니다. query 로 제목·제공 기관을 거를 수 있습니다. 처음에 한 번 불러 보세요."""
    q = query.strip()
    return [
        {"id": a["id"], "title": a["title"], "provider": a["provider"], "verified_spec": bool(a.get("verified"))}
        for a in REG.values()
        if not q or q in a["title"] or q in a["provider"] or q in a["id"]
    ]


@mcp.tool()
def describe_api(api_id: str) -> dict:
    """API 의 인자(필수 여부·설명), 응답 형식, 캐시 시간, 활용 신청 페이지를 돌려줍니다. call_api 전에 확인하세요."""
    a = REG.get(api_id)
    if not a:
        return {"error": f"'{api_id}' 는 등록된 API 가 아닙니다. list_apis 로 id 를 확인하세요."}
    return {
        "id": a["id"],
        "title": a["title"],
        "provider": a["provider"],
        "doc": a.get("doc"),
        "params": a.get("params", []),
        "format": a["format"],
        "cache_seconds": a.get("cache_seconds", 0),
        "verified_spec": bool(a.get("verified")),
        "note": None
        if a.get("verified")
        else "응답 형식을 실제 호출로 확인하지 않은 API 입니다. 항목 이름은 받은 그대로 돌려줍니다.",
    }


@mcp.tool()
def call_api(api_id: str, params: dict | None = None, max_rows: int = 100) -> dict:
    """등록된 API 를 호출해 항목을 돌려줍니다 (최대 1000행). 같은 인자는 API 마다 정한 시간 동안 캐시에서 돌려줍니다.
    오류면 원인과 해결 방법을 담은 error 를 돌려줍니다."""
    a = REG.get(api_id)
    if not a:
        return {"error": f"'{api_id}' 는 등록된 API 가 아닙니다. list_apis 로 id 를 확인하세요."}
    try:
        return client.call(a, params or {}, max_rows, cache=CACHE)
    except (client.ApiError, ValueError, RuntimeError) as e:
        return {"error": client.redact(str(e), os.environ.get(client.KEY_ENV))}


@mcp.tool()
def cache_status() -> dict:
    """캐시에 저장된 응답 수와 가장 오래된 항목의 나이(초)."""
    return CACHE.stats()


if __name__ == "__main__":
    mcp.run()
