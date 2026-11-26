import json
import os
import sys
from pathlib import Path

import anyio
import pytest

from pubdata import client

REG = client.load_registry()
KEY = "SECRET+KEY/abc=="


class Resp:
    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def xml_page(items, total, code="00"):
    rows = "".join("<item>" + "".join(f"<{k}>{v}</{k}>" for k, v in it.items()) + "</item>" for it in items)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><response><header><resultCode>{code}</resultCode><resultMsg>MSG</resultMsg></header>'
        f"<body><items>{rows}</items><totalCount>{total}</totalCount></body></response>"
    ).encode()


def test_registry_is_valid_and_only_allowed_hosts():
    assert {"er_list", "er_beds", "air_sido", "weather_forecast", "weather_now", "holidays"} <= set(REG)
    for a in REG.values():
        assert a["format"] in ("xml", "json") and a["page_param"] and a["size_param"] and a["items"]
        assert all({"name", "required", "description"} <= set(p) for p in a["params"])


def test_registry_rejects_foreign_host(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text(
        "apis:\n  - {id: x, title: t, provider: p, url: 'https://evil.example.com/api', format: xml, items: item, page_param: pageNo, size_param: numOfRows, params: []}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="허용되지 않은 주소"):
        client.load_registry(p)


def test_params_validation():
    a = REG["er_beds"]
    with pytest.raises(ValueError, match="필수 인자"):
        client.check_params(a, {})
    with pytest.raises(ValueError, match="등록되지 않은 인자"):
        client.check_params(a, {"STAGE1": "경상북도", "serviceKey": "x"})  # 키를 인자로 몰래 넣는 것도 막음
    assert client.check_params(a, {"STAGE1": "경상북도", "STAGE2": ""}) == {"STAGE1": "경상북도"}


def test_build_url_includes_fixed_params_and_key():
    url = client.build_url(REG["air_sido"], {"sidoName": "경북"}, 2, 50, KEY)
    assert (
        "returnType=json" in url
        and "pageNo=2" in url
        and "numOfRows=50" in url
        and "sidoName=%EA%B2%BD%EB%B6%81" in url
    )
    assert "serviceKey=SECRET%2BKEY%2Fabc%3D%3D" in url


def test_redact_hides_key_in_all_forms():
    msg = f"failed https://apis.data.go.kr/x?serviceKey=SECRET%2BKEY%2Fabc%3D%3D&a=1 raw={KEY}"
    out = client.redact(msg, KEY)
    assert "SECRET" not in out and "serviceKey=***" in out


def test_parse_xml_items_and_total():
    items, total = client.parse(REG["er_list"], xml_page([{"dutyName": "가병원", "hpid": "A1"}], 7))
    assert items == [{"dutyName": "가병원", "hpid": "A1"}] and total == 7


def test_parse_errors_both_formats():
    with pytest.raises(client.ApiError) as e:
        client.parse(REG["er_list"], xml_page([], 0, code="22"))
    assert "요청 횟수 초과" in str(e.value)
    gw = b"<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"
    with pytest.raises(client.ApiError) as e2:
        client.parse(REG["er_list"], gw)
    assert e2.value.code == "30" and "Decoding" in str(e2.value)


def test_parse_json_including_single_item_object():
    body = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {"items": {"item": {"category": "TMP", "fcstValue": "3"}}, "totalCount": 1},
        }
    }
    items, total = client.parse(REG["weather_forecast"], json.dumps(body).encode())
    assert items == [{"category": "TMP", "fcstValue": "3"}] and total == 1
    bad = {"response": {"header": {"resultCode": "03", "resultMsg": "NO_DATA"}}}
    with pytest.raises(client.ApiError, match="데이터 없음"):
        client.parse(REG["weather_forecast"], json.dumps(bad).encode())


def test_call_pages_until_total_and_caps_rows(tmp_path):
    seen = []

    def opener(url, timeout=0):
        seen.append(url)
        page = int(url.split("pageNo=")[1].split("&")[0])
        return Resp(xml_page([{"n": f"{page}-{i}"} for i in range(3)], 7 if page < 3 else 7))

    r = client.call(REG["er_list"], {"Q0": "경상북도"}, max_rows=5, key=KEY, opener=opener, page_size=3)
    assert r["returned"] == 5 and r["total"] == 7 and r["truncated"] is True and r["pages"] == 2
    assert KEY not in json.dumps(r) and "SECRET" not in json.dumps(r)


def test_call_uses_cache_and_missing_key_message(tmp_path):
    cache = client.Cache(tmp_path / "c.sqlite")
    n = {"calls": 0}

    def opener(url, timeout=0):
        n["calls"] += 1
        return Resp(xml_page([{"locdate": "20261225", "dateName": "기독탄신일"}], 1))

    a = REG["holidays"]
    r1 = client.call(a, {"solYear": "2026"}, key=KEY, cache=cache, opener=opener)
    r2 = client.call(a, {"solYear": "2026"}, key=KEY, cache=cache, opener=opener)
    assert (r1["cached"], r2["cached"], n["calls"]) == (False, True, 1)
    assert r2["items"][0]["dateName"] == "기독탄신일" and cache.stats()["entries"] == 1
    with pytest.raises(ValueError, match="DATA_GO_KR_KEY"):
        client.call(a, {"solYear": "2026"}, key="", opener=opener)


def test_network_error_message_does_not_leak_key():
    def opener(url, timeout=0):
        raise OSError(f"connection reset while fetching {url}")

    with pytest.raises(RuntimeError) as e:
        client.call(REG["er_list"], {}, key=KEY, opener=opener)
    assert "SECRET" not in str(e.value) and "***" in str(e.value)


def test_mcp_server_over_stdio(tmp_path):
    """실제 MCP 프로토콜(stdio)로 서버를 띄워 도구를 불러 봄 (인증키 없이: 목록·설명은 되고 호출은 친절한 오류)"""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {k: v for k, v in os.environ.items() if k != client.KEY_ENV}
    env["PUBDATA_CACHE"] = str(tmp_path / "cache.sqlite")
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "pubdata.server"], cwd=str(Path(__file__).resolve().parent.parent), env=env
    )

    async def go():
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = sorted(t.name for t in (await s.list_tools()).tools)
                res = await s.call_tool("list_apis", {"query": "기상청"})
                apis = [json.loads(c.text) for c in res.content]  # FastMCP 는 목록을 항목마다 한 조각으로 보냄
                desc = json.loads((await s.call_tool("describe_api", {"api_id": "er_beds"})).content[0].text)
                err = json.loads(
                    (await s.call_tool("call_api", {"api_id": "er_beds", "params": {"STAGE1": "경상북도"}}))
                    .content[0]
                    .text
                )
                bad = json.loads((await s.call_tool("describe_api", {"api_id": "nope"})).content[0].text)
                return names, apis, desc, err, bad

    names, apis, desc, err, bad = anyio.run(go)
    assert names == ["cache_status", "call_api", "describe_api", "list_apis"]
    apis = [x for a in apis for x in (a if isinstance(a, list) else [a])]
    assert {a["id"] for a in apis} == {"weather_forecast", "weather_now"}
    assert desc["params"][0]["name"] == "STAGE1" and desc["verified_spec"] is False
    assert "DATA_GO_KR_KEY" in err["error"] and "list_apis" in bad["error"]
