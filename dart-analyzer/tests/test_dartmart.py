"""모든 테스트는 가상 데이터(tests/fixtures)와 가짜 클라이언트로 돌고, 실제 DART 에 접속하지 않습니다."""
import io
import json
import zipfile
from pathlib import Path

import pytest

from dartmart import client as dclient, parse, pipeline, search

FIX = Path(__file__).parent / "fixtures"


class FakeClient:
    def __init__(self):
        self.fin = json.loads((FIX / "financials.json").read_text(encoding="utf-8"))

    def corp_codes(self):
        return parse.parse_corp_codes((FIX / "corpcode.xml").read_bytes())

    def financials(self, corp_code, year, reprt="사업보고서"):
        return self.fin.get(corp_code, {}).get(str(year), [])

    def filings(self, corp_code, bgn, end, kind="A"):
        return [{"rcept_no": f"R{corp_code}", "report_nm": "사업보고서 (2025.12)", "rcept_dt": "20260320"}]

    def document(self, rcept_no):
        return [(FIX / "document.xml").read_bytes()]


@pytest.fixture
def con(tmp_path):
    c = pipeline.connect(tmp_path / "t.sqlite")
    cfg = {"companies": {"테스트": ["예시전자", "예시에너지", "없는회사"]}}
    stats = pipeline.load(c, FakeClient(), cfg, [2024, 2025], log=lambda *a: None)
    assert stats["companies"] == 2           # 없는회사는 건너뜀
    return c


def test_amount_parsing():
    assert parse.amount("1,234,567") == 1234567
    assert parse.amount("(1,234)") == -1234
    assert parse.amount("-500") == -500
    assert parse.amount("") is None and parse.amount("-") is None and parse.amount(None) is None


def test_resolve_prefers_listed_company():
    corps = FakeClient().corp_codes()
    got = pipeline.resolve(corps, ["예시에너지"], log=lambda *a: None)
    assert got["예시에너지"]["corp_code"] == "00000002"


def test_normalize_prefers_consolidated():
    rows = FakeClient().financials("00000002", 2024)
    norm = {r["account"]: r for r in parse.normalize_financials(rows)}
    assert norm["revenue"]["fs_div"] == "CFS" and norm["revenue"]["amount"] == 50_000_000_000


def test_metrics_view_margin_and_growth(con):
    m = con.execute("SELECT op_margin_pct, debt_ratio_pct FROM v_metrics WHERE corp_name='예시전자' AND bsns_year=2024").fetchone()
    assert m == (10.0, 62.5)
    g = con.execute("SELECT revenue_yoy_pct, op_income_yoy_pct FROM v_growth WHERE corp_name='예시전자' AND bsns_year=2025").fetchone()
    assert g == (20.0, -10.0)
    first = con.execute("SELECT revenue_yoy_pct FROM v_growth WHERE corp_name='예시전자' AND bsns_year=2024").fetchone()
    assert first == (None,)


def test_sector_rank(con):
    r = con.execute("SELECT corp_name, margin_rank FROM v_sector_rank WHERE bsns_year=2024 ORDER BY margin_rank").fetchall()
    assert [x[1] for x in r] == [1, 1]          # 둘 다 10% → 공동 1위


def test_document_sections_skips_short_and_keeps_titles():
    paras = parse.document_sections((FIX / "document.xml").read_bytes())
    assert all(len(p["text"]) >= 30 for p in paras)
    assert paras[0]["section"] == "II. 사업의 내용"
    assert paras[-1]["section"] == "III. 재무에 관한 사항"


def test_document_sections_falls_back_on_broken_xml():
    broken = b"<DOCUMENT><TITLE>II. \xec\x82\xac\xec\x97\x85</TITLE><P>" + ("가" * 40).encode() + b"<BR></P></DOCUMENT"
    paras = parse.document_sections(broken)
    assert len(paras) == 1 and paras[0]["section"].startswith("II.")


def test_ask_returns_cited_paragraph(con):
    hits = pipeline.ask(con, "예시에너지", "LNG 판매 물량")
    assert hits and "LNG 판매 물량" in hits[0]["text"]
    assert hits[0]["report_nm"].startswith("사업보고서") and hits[0]["rcept_no"]


def test_ask_returns_nothing_when_unrelated(con):
    assert pipeline.ask(con, "예시에너지", "비트코인 채굴 장비") == []


def test_bigram_tokens_handle_korean_particles():
    assert set(search.tokens("가스전을")) >= {"가스", "스전"}
    assert "lng" in search.tokens("LNG 도입")


def test_client_requires_key(monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    with pytest.raises(dclient.DartError):
        dclient.Client()


def _resp(body: bytes):
    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    return R(body)


def test_client_status_handling():
    bodies = iter([json.dumps({"status": "020", "message": "limit"}).encode(), json.dumps({"status": "000", "list": [1]}).encode(),
                   json.dumps({"status": "013", "message": "no data"}).encode(), json.dumps({"status": "100", "message": "bad"}).encode()])
    c = dclient.Client(key="dummy", opener=lambda req, timeout=60: _resp(next(bodies)), sleep=lambda s: None, min_interval=0)
    assert c.json("x.json", {})["list"] == [1]              # 020 → 대기 후 재시도
    assert c.json("x.json", {})["list"] == []               # 013 → 빈 결과
    with pytest.raises(dclient.DartError):
        c.json("x.json", {})


def test_client_zip_error_message():
    c = dclient.Client(key="dummy", opener=lambda req, timeout=60: _resp(b'{"status":"010","message":"bad key"}'), sleep=lambda s: None, min_interval=0)
    with pytest.raises(dclient.DartError):
        c.zip("document.xml", {"rcept_no": "1"})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.xml", "<x/>")
    c2 = dclient.Client(key="dummy", opener=lambda req, timeout=60: _resp(buf.getvalue()), sleep=lambda s: None, min_interval=0)
    assert c2.document("1") == [b"<x/>"]


def test_report_table(con):
    md = pipeline.report(con)
    assert "| 테스트 | 예시전자 | 2025 | 1,200 | 90 | 7.5% | +20.0% |" in md


def test_resolve_with_stock_code_disambiguates():
    corps = FakeClient().corp_codes() + [{"corp_code": "00000009", "corp_name": "예시전자", "stock_code": "999999", "modify_date": ""}]
    assert pipeline.resolve(corps, ["예시전자"], log=lambda *a: None) == {}          # 상장사 2곳 → 건너뜀
    got = pipeline.resolve(corps, ["예시전자#999999"], log=lambda *a: None)
    assert got["예시전자"]["corp_code"] == "00000009"


def test_missing_document_is_skipped(tmp_path):
    class NoDoc(FakeClient):
        def document(self, rcept_no):
            raise dclient.NoFile("document.xml: 파일 없음 (014)")
    c = pipeline.connect(tmp_path / "t.sqlite")
    stats = pipeline.load(c, NoDoc(), {"companies": {"t": ["예시전자"]}}, [2024], log=lambda *a: None)
    assert stats["companies"] == 1 and stats["paragraphs"] == 0 and stats["financial_rows"] > 0


def test_client_detects_014_xml():
    body = '<?xml version="1.0"?><result><status>014</status><message>파일이 존재하지 않습니다.</message></result>'.encode()
    c = dclient.Client(key="dummy", opener=lambda req, timeout=60: _resp(body), sleep=lambda s: None, min_interval=0)
    with pytest.raises(dclient.NoFile):
        c.document("1")
