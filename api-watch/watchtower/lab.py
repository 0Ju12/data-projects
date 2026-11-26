"""Deterministic synthetic failures, evaluated by the production detector."""

import json
from datetime import datetime, timedelta, timezone

from .engine import evaluate


def exercise():
    now = datetime.now(timezone.utc)
    spec = {
        "required": {"updated": "string", "items": "array"},
        "records_path": "items",
        "record_required": {"id": "string", "value": "number"},
        "id_path": "id",
        "min_records": 1,
        "freshness_path": "updated",
        "time_format": "iso",
        "max_age_seconds": 3600,
        "numeric_rules": {},
        "warning_latency_ms": 3000,
    }
    base = {"updated": now.isoformat(), "items": [{"id": "one", "value": 1}]}
    response = {"status": 200, "duration_ms": 100, "body": json.dumps(base), "error": ""}
    baseline = evaluate(spec, response, now)["observed"]
    cases = []

    def add(name, payload, expected, status=200, error="", ms=100):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        result = evaluate(spec, {"status": status, "duration_ms": ms, "body": body, "error": error}, now, baseline)
        failed = [x["key"] for x in result["checks"] if not x["ok"]]
        ok = (not failed) if expected is None else expected in failed
        cases.append(
            {
                "name": name,
                "expected": expected,
                "detected": failed,
                "passed": ok,
                "checks": result["checks"],
                "payload": payload,
                "http_status": status,
            }
        )

    add("정상 응답", base, None)
    add("HTTP 503", base, "availability", 503)
    add("잘못된 JSON", "<html>upstream error</html>", "json")
    add("HTTP 200 · 빈 목록", dict(base, items=[]), "count")
    add("HTTP 200 · 오래된 자료", dict(base, updated=(now - timedelta(days=3)).isoformat()), "freshness")
    add("중복 식별자", dict(base, items=[{"id": "one", "value": 1}, {"id": "one", "value": 2}]), "duplicates")
    add("자료형 변경", dict(base, items=[{"id": "one", "value": "1"}]), "record:value")
    add("필수 필드 누락", {"items": base["items"]}, "field:updated")
    add("미래 시각", dict(base, updated=(now + timedelta(hours=2)).isoformat()), "future-time")
    add("응답 지연", base, "latency", ms=5000)
    return {
        "source": "synthetic",
        "executed_at": now.isoformat(),
        "description": "합성 응답을 실제 검사 엔진에 넣은 결과입니다. 운영 장애·모델 성능 수치가 아닙니다.",
        "cases": cases,
        "passed": sum(c["passed"] for c in cases),
        "total": len(cases),
    }
