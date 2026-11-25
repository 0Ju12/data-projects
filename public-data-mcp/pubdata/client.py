"""등록부(registry.yaml)에 있는 공공데이터포털 API 만 호출한다.

지키는 것
- 등록된 API·인자만: 모르는 API id, 등록 안 된 인자, 등록부 밖 주소는 거부
- 인증키는 환경변수(DATA_GO_KR_KEY)로만 받고, 돌려주는 값·오류·캐시 키 어디에도 남기지 않음
- 공공데이터포털 오류 코드를 사람이 읽는 원인·해결로 바꿈 (일반 응답·게이트웨이 응답 두 형식 모두)
- 페이지를 넘겨 가며 모으되 max_rows 에서 멈춤, 같은 호출은 등록부의 cache_seconds 동안 캐시
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "registry.yaml"
KEY_ENV = "DATA_GO_KR_KEY"
ALLOWED_HOSTS = {"apis.data.go.kr", "api.odcloud.kr"}
MAX_ROWS = 1000

# 공공데이터포털 공통 오류 코드 → (뜻, 해결)
ERRORS = {
    "01": ("어플리케이션 오류", "제공 기관 서버 문제입니다. 잠시 뒤 다시 시도하세요."),
    "02": ("데이터베이스 오류", "제공 기관 서버 문제입니다. 잠시 뒤 다시 시도하세요."),
    "03": ("데이터 없음", "조건에 맞는 자료가 없습니다. 인자 값을 바꿔 보세요."),
    "04": ("HTTP 오류", "제공 기관 서버 문제입니다. 잠시 뒤 다시 시도하세요."),
    "05": ("서비스 연결 실패", "제공 기관 서버가 응답하지 않습니다. 잠시 뒤 다시 시도하세요."),
    "10": ("잘못된 요청 인자", "describe_api 로 인자 이름과 형식을 확인하세요."),
    "11": ("필수 인자 없음", "describe_api 로 필수 인자를 확인하세요."),
    "12": ("해당 서비스 없음", "API 주소가 바뀌었을 수 있습니다. registry.yaml 의 url 을 확인하세요."),
    "20": ("서비스 접근 거부", "이 API 에 활용 신청이 승인됐는지 확인하세요."),
    "21": ("일시적으로 사용할 수 없는 인증키", "공공데이터포털에서 인증키 상태를 확인하세요."),
    "22": ("요청 횟수 초과", "하루 호출 한도를 넘었습니다. 캐시된 결과를 쓰거나 내일 다시 시도하세요."),
    "30": ("등록되지 않은 인증키", "DATA_GO_KR_KEY 에 '일반 인증키(Decoding)' 를 넣었는지, 활용 신청 후 1시간이 지났는지 확인하세요."),
    "31": ("활용 기간 만료", "공공데이터포털에서 활용 기간을 연장하세요."),
    "32": ("등록되지 않은 IP", "인증키에 허용 IP 를 등록했다면 지금 IP 를 추가하세요."),
    "33": ("서명되지 않은 호출", "인증키 형식을 확인하세요."),
    "99": ("알 수 없는 오류", "잠시 뒤 다시 시도하세요."),
}


class ApiError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        meaning, fix = ERRORS.get(code, ("오류", ""))
        super().__init__(f"[{code}] {meaning}: {message}" + (f" — {fix}" if fix else ""))


def load_registry(path: Path = REGISTRY) -> dict[str, dict]:
    apis = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["apis"]
    out = {}
    for a in apis:
        host = urllib.parse.urlparse(a["url"]).hostname
        if host not in ALLOWED_HOSTS:
            raise ValueError(f"{a['id']}: 허용되지 않은 주소 {host}")
        out[a["id"]] = a
    return out


def redact(text: str, key: str | None) -> str:
    """오류·로그에 인증키가 섞이지 않게 (원문과 URL 인코딩 형태 모두)."""
    if not key:
        return text
    for k in {key, urllib.parse.quote(key, safe=""), urllib.parse.quote_plus(key)}:
        text = text.replace(k, "***")
    return re.sub(r"(serviceKey=)[^&\s]+", r"\1***", text)


def check_params(api: dict, params: dict) -> dict:
    allowed = {p["name"]: p for p in api.get("params", [])}
    unknown = sorted(set(params) - set(allowed))
    if unknown:
        raise ValueError(f"등록되지 않은 인자 {unknown} — 쓸 수 있는 인자: {sorted(allowed)}")
    missing = [n for n, p in allowed.items() if p.get("required") and str(params.get(n, "")).strip() == ""]
    if missing:
        raise ValueError(f"필수 인자 없음: {missing}")
    return {k: str(v) for k, v in params.items() if str(v).strip() != ""}


def build_url(api: dict, params: dict, page: int, size: int, key: str) -> str:
    q = {**api.get("fixed", {}), **params, api["page_param"]: page, api["size_param"]: size, api.get("key_param", "serviceKey"): key}
    return f"{api['url']}?{urllib.parse.urlencode(q)}"


def _dig(obj, path: str):
    for part in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def parse(api: dict, body: bytes) -> tuple[list[dict], int | None]:
    """응답 → (항목, 전체 건수). 오류 응답이면 ApiError."""
    text = body.decode("utf-8", errors="replace").strip()
    if text.startswith("<"):
        root = ET.fromstring(text)
        # 게이트웨이 형식: <OpenAPI_ServiceResponse><cmmMsgHeader><returnReasonCode>30</…>
        gw = root.findtext(".//returnReasonCode")
        if gw and gw != "00":
            raise ApiError(gw, root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg") or "")
        code = root.findtext(".//resultCode")
        if code not in (None, "00", "0000", "INFO-000"):
            raise ApiError(code, root.findtext(".//resultMsg") or "")
        tag = api.get("items", "item")
        items = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter(tag)]
        total = root.findtext(f".//{api.get('total', 'totalCount')}")
        return items, int(total) if total and total.strip().isdigit() else None
    data = json.loads(text)
    code = _dig(data, "response.header.resultCode")
    if code not in (None, "00", "0000"):
        raise ApiError(str(code), str(_dig(data, "response.header.resultMsg") or ""))
    items = _dig(data, api["items"]) or []
    if isinstance(items, dict):                 # 한 건이면 목록이 아니라 객체로 오는 API 가 있음
        items = [items]
    total = _dig(data, api["total"]) if api.get("total") else None
    return items, int(total) if total is not None and str(total).isdigit() else None


class Cache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, saved REAL, body TEXT)")

    @staticmethod
    def key(api_id: str, params: dict, max_rows: int) -> str:     # 인증키는 넣지 않음
        return hashlib.sha256(json.dumps([api_id, sorted(params.items()), max_rows], ensure_ascii=False).encode()).hexdigest()

    def get(self, k: str, ttl: float) -> dict | None:
        row = self.con.execute("SELECT saved, body FROM cache WHERE k = ?", (k,)).fetchone()
        if row and time.time() - row[0] < ttl:
            return json.loads(row[1])
        return None

    def put(self, k: str, value: dict) -> None:
        self.con.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (k, time.time(), json.dumps(value, ensure_ascii=False)))
        self.con.commit()

    def stats(self) -> dict:
        n, oldest = self.con.execute("SELECT COUNT(*), MIN(saved) FROM cache").fetchone()
        return {"entries": n, "oldest_age_s": round(time.time() - oldest) if oldest else None}


def call(api: dict, params: dict, max_rows: int = 100, key: str | None = None, cache: Cache | None = None,
         opener=urllib.request.urlopen, page_size: int = 100) -> dict:
    """API 를 불러 항목을 모은다. 돌려주는 값에는 인증키가 없다."""
    key = key if key is not None else os.environ.get(KEY_ENV, "")
    if not key:
        raise ValueError(f"환경변수 {KEY_ENV} 에 공공데이터포털 인증키(일반 인증키, Decoding)를 넣어 주세요.")
    params = check_params(api, params)
    max_rows = max(1, min(int(max_rows), MAX_ROWS))
    ck = Cache.key(api["id"], params, max_rows)
    if cache:
        hit = cache.get(ck, api.get("cache_seconds", 0))
        if hit:
            return {**hit, "cached": True}
    items, total, page, pages = [], None, 1, 0
    size = min(page_size, max_rows)
    while len(items) < max_rows:
        url = build_url(api, params, page, size, key)
        try:
            with opener(url, timeout=30) as r:
                body = r.read()
        except ApiError:
            raise
        except Exception as e:                     # 네트워크 오류 메시지에 URL(=키)이 섞일 수 있음
            raise RuntimeError(redact(f"{api['id']} 호출 실패: {e}", key)) from None
        batch, total = parse(api, body)
        pages += 1
        items += batch
        if not batch or (total is not None and len(items) >= total) or len(batch) < size:
            break
        page += 1
    result = {"api": api["id"], "title": api["title"], "params": params, "total": total,
              "returned": min(len(items), max_rows), "truncated": total is not None and total > max_rows,
              "pages": pages, "items": items[:max_rows], "verified_spec": bool(api.get("verified"))}
    if cache:
        cache.put(ck, result)
    return {**result, "cached": False}
