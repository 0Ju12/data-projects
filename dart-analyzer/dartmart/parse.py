"""DART 응답 정리: 회사 코드 XML, 금액 문자열, 공시 원문 XML → 절(section)·문단."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET


def parse_corp_codes(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out = []
    for el in root.iter("list"):
        g = lambda k: (el.findtext(k) or "").strip()
        out.append({"corp_code": g("corp_code"), "corp_name": g("corp_name"), "stock_code": g("stock_code"), "modify_date": g("modify_date")})
    return out


def amount(s) -> int | None:
    """'1,234,567' · '-1,234' · '(1,234)' · '' → 정수 또는 None"""
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if s in ("", "-"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = int(float(s))
    except ValueError:
        return None
    return -v if neg else v


ACCOUNTS = {   # 회사마다 계정명이 조금씩 달라 표준 이름으로 묶음
    "매출액": "revenue", "수익(매출액)": "revenue", "영업수익": "revenue", "매출": "revenue",
    "영업이익": "operating_income", "영업이익(손실)": "operating_income",
    "당기순이익": "net_income", "당기순이익(손실)": "net_income",
    "자산총계": "total_assets", "부채총계": "total_liabilities", "자본총계": "total_equity",
}


def normalize_financials(rows: list[dict]) -> list[dict]:
    """fnlttSinglAcnt 응답 → 표준 계정만 (연결 CFS 우선, 없으면 별도 OFS)"""
    out = {}
    for r in rows:
        std = ACCOUNTS.get((r.get("account_nm") or "").replace(" ", ""))
        if not std:
            continue
        key = (r["corp_code"], int(r["bsns_year"]), std)
        rec = {"corp_code": r["corp_code"], "bsns_year": int(r["bsns_year"]), "account": std, "fs_div": r.get("fs_div", ""),
               "amount": amount(r.get("thstrm_amount")), "prev_amount": amount(r.get("frmtrm_amount")), "rcept_no": r.get("rcept_no", "")}
        if key not in out or (out[key]["fs_div"] != "CFS" and rec["fs_div"] == "CFS"):
            out[key] = rec
    return list(out.values())


def _text(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def document_sections(xml_bytes: bytes, min_len: int = 30) -> list[dict]:
    """공시 원문 XML → [{section, para_no, text}]. TITLE 을 만나면 절이 바뀌고, P·TD 문단을 모음.
    DART 원문은 HTML 에 가까운 XML 이라 엄격 파서가 실패하면 태그를 정규식으로 걷어 내는 방식으로 대체합니다."""
    try:
        root = ET.fromstring(xml_bytes)
        items = []
        section = ""
        for el in root.iter():
            tag = el.tag.upper() if isinstance(el.tag, str) else ""
            if tag == "TITLE":
                section = _text(el)
            elif tag in ("P", "TD"):
                t = _text(el)
                if len(t) >= min_len:
                    items.append((section, t))
    except ET.ParseError:
        s = xml_bytes.decode("utf-8", "ignore")
        items, section = [], ""
        for m in re.finditer(r"<(TITLE|P)[^>]*>(.*?)</\1>", s, re.S | re.I):
            t = re.sub(r"<[^>]+>", " ", m.group(2))
            t = re.sub(r"\s+", " ", t).strip()
            if m.group(1).upper() == "TITLE":
                section = t
            elif len(t) >= min_len:
                items.append((section, t))
    out, seen = [], set()
    for sec, t in items:
        if t in seen:
            continue
        seen.add(t)
        out.append({"section": sec, "para_no": len(out), "text": t})
    return out
