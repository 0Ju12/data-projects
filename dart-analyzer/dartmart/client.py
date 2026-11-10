"""OpenDART(금융감독원 전자공시) API 클라이언트.

- 인증키는 환경변수 DART_API_KEY 로만 받습니다 (코드·로그·저장소에 남기지 않음).
- 응답 status: '000' 정상, '013' 조회 데이터 없음(빈 결과로 처리), '020' 요청 한도 초과(대기 후 재시도), 그 밖은 예외.
- 한도(일 20,000건)를 지키기 위해 요청 사이에 최소 간격을 둡니다.
"""
from __future__ import annotations

import io
import json
import os
import time
import urllib.parse
import urllib.request
import zipfile

BASE = "https://opendart.fss.or.kr/api/"
REPRT = {"사업보고서": "11011", "반기보고서": "11012", "1분기보고서": "11013", "3분기보고서": "11014"}


class DartError(RuntimeError):
    pass


class NoFile(DartError):
    """014: 원문 파일이 없음 (정정·첨부 등 일부 공시) — 그 회사 원문만 건너뛰면 됨"""


class Client:
    def __init__(self, key: str | None = None, opener=urllib.request.urlopen, min_interval: float = 0.15, sleep=time.sleep):
        self.key = key or os.environ.get("DART_API_KEY", "")
        if not self.key:
            raise DartError("DART_API_KEY 가 없습니다. https://opendart.fss.or.kr 에서 인증키를 발급해 환경변수로 넣으세요.")
        self.opener, self.min_interval, self.sleep, self._last = opener, min_interval, sleep, 0.0

    def _raw(self, path: str, params: dict) -> bytes:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            self.sleep(wait)
        q = urllib.parse.urlencode({"crtfc_key": self.key, **params})
        req = urllib.request.Request(BASE + path + "?" + q, headers={"User-Agent": "dart-analyzer/1.0"})
        with self.opener(req, timeout=60) as r:
            body = r.read()
        self._last = time.monotonic()
        return body

    def json(self, path: str, params: dict, retries: int = 3) -> dict:
        for attempt in range(retries + 1):
            d = json.loads(self._raw(path, params).decode("utf-8"))
            st = d.get("status")
            if st == "000":
                return d
            if st == "013":
                return {"status": "013", "list": []}
            if st == "020" and attempt < retries:
                self.sleep(60 * (attempt + 1))
                continue
            raise DartError(f"{path} status={st} {d.get('message', '')}")
        raise DartError("unreachable")

    def zip(self, path: str, params: dict) -> zipfile.ZipFile:
        body = self._raw(path, params)
        if body[:2] != b"PK":                       # 오류면 zip 대신 JSON/XML 메시지가 옴
            msg = body[:300].decode("utf-8", "ignore")
            if "<status>014</status>" in msg or '"status":"014"' in msg:
                raise NoFile(f"{path}: 파일 없음 (014)")
            raise DartError(f"{path}: {msg[:200]}")
        return zipfile.ZipFile(io.BytesIO(body))

    # --- 엔드포인트 ---
    def corp_codes(self) -> list[dict]:
        """전체 회사 고유번호 목록 (corpCode.xml)"""
        from .parse import parse_corp_codes
        z = self.zip("corpCode.xml", {})
        return parse_corp_codes(z.read(z.namelist()[0]))

    def filings(self, corp_code: str, bgn_de: str, end_de: str, kind: str = "A") -> list[dict]:
        """정기공시(A) 목록. 여러 쪽이면 모두 받음"""
        out, page = [], 1
        while True:
            d = self.json("list.json", {"corp_code": corp_code, "bgn_de": bgn_de, "end_de": end_de, "pblntf_ty": kind,
                                        "page_no": page, "page_count": 100})
            out += d.get("list", [])
            if page >= int(d.get("total_page", 1) or 1):
                return out
            page += 1

    def financials(self, corp_code: str, year: int, reprt: str = "사업보고서") -> list[dict]:
        """단일회사 주요 계정 (연결·별도 둘 다 옴)"""
        return self.json("fnlttSinglAcnt.json", {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": REPRT[reprt]}).get("list", [])

    def document(self, rcept_no: str) -> list[bytes]:
        """공시 원문 XML 파일들"""
        z = self.zip("document.xml", {"rcept_no": rcept_no})
        return [z.read(n) for n in z.namelist() if n.lower().endswith(".xml")]
