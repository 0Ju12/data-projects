import datetime as dt
import json
from pathlib import Path

from jobcal import classify as C, feed, sources as S

FX = Path(__file__).parent / "fixtures"


def fx(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def test_roles_multi_and_boundaries():
    assert C.roles("데이터 플랫폼 백엔드 개발자") == ["데이터·AI", "백엔드"]
    assert C.roles("Android Developer") == ["모바일"]
    assert C.roles("Email Marketing Manager") == ["기타"]          # 'AI' 가 Email 안에서 잡히면 안 됨
    assert C.roles("AI 컴파일러 엔지니어 (신입)") == ["데이터·AI", "임베디드·하드웨어"]
    assert "보안" in C.roles("Security Engineer Intern")


def test_newbie_flags():
    assert C.newbie("Backend Engineer", flag=True) is True
    assert C.newbie("Software Engineer, New Grad") is True
    assert C.newbie("백엔드 개발자 (경력 5년 이상)") is False
    assert C.newbie("Staff Security Engineer") is False
    assert C.newbie("Backend Engineer") is None                   # 표시 없음은 모름으로 둠
    assert C.newbie("체험형 인턴 (경력 무관)") is True


def test_tech_filter():
    assert C.tech("Data Analyst") is True
    assert C.tech("[쿠팡] 운송 파트너사 관리 담당자") is False
    assert C.tech("AI Business Development (10년 이상)") is False   # 사업 개발은 AI 가 붙어도 개발 직군 아님
    assert C.tech("Business Development Engineer") is True


def test_sources_normalize_fixtures():
    j = S.jumpit_rows(fx("jumpit.json"))
    assert j and all(r["id"].startswith("jumpit:") and r["url"].startswith("https://jumpit.saramin.co.kr/position/") for r in j)
    assert all(r["newbie"] is True for r in j)                     # career=0 목록
    assert all(r["end"] is None or len(r["end"]) == 10 for r in j)
    k = S.kakao_rows(fx("kakao.json"))
    assert k and all(not r["title"].startswith("[공동체]") for r in k)
    g = S.greenhouse_rows("krafton", fx("greenhouse.json"))
    assert g and all(r["co"] == "크래프톤" and r["start"] for r in g)
    assert S.greenhouse_rows("krafton", {"jobs": [{"id": 1, "title": "x", "location": {"name": "Austin, TX"}}]}) == []   # 국내만


def row(i, end=None, src="점핏"):
    return {"id": f"jumpit:{i}", "src": src, "co": "회사", "title": f"공고 {i}", "url": "u", "roles": ["백엔드"], "stacks": [],
            "loc": "서울", "newbie": True, "start": None, "end": end, "tech": True}


def test_merge_keeps_first_seen_and_counts():
    st, d1, d2 = {}, dt.date(2026, 11, 20), dt.date(2026, 11, 24)
    assert feed.merge(st, [row(1), row(2)], d1) == (2, 0)
    changed = dict(row(1), title="공고 1 (수정)")
    assert feed.merge(st, [changed], d2) == (0, 1)
    assert st["jumpit:1"]["first_seen"] == "2026-11-20" and st["jumpit:1"]["last_seen"] == "2026-11-24"


def test_prune_rules():
    today = dt.date(2026, 11, 24)
    st = {}
    feed.merge(st, [row(1, end="2026-10-01"), row(2), row(3, end="2026-12-10")], dt.date(2026, 11, 20))
    feed.merge(st, [row(4)], today)
    # 1: 마감 30일 넘게 지남 → 뺌 / 2·3: 마감 전인데 나흘째 목록에 없음 → 조기 마감으로 뺌 / 4: 오늘 봄
    assert feed.prune(st, today, {"jumpit"}) == 3 and set(st) == {"jumpit:4"}
    st2 = {}
    feed.merge(st2, [row(2)], dt.date(2026, 11, 20))
    assert feed.prune(st2, today, set()) == 0                      # 그 출처 수집이 실패한 날엔 지우지 않음


def test_export_shape(tmp_path):
    st, today = {}, dt.date(2026, 11, 24)
    feed.merge(st, [row(1, end="2026-12-01"), row(2)], today)
    out = feed.export(st, [{"src": "점핏", "n": 2, "ok": True}], today, path=tmp_path / "jobs.json")
    assert out["count"] == 2 and out["postings"][0]["end"] == "2026-12-01"   # 마감 빠른 순, 상시는 뒤
    assert out["postings"][1]["start"] == "2026-11-24"                     # 등록일 없으면 처음 본 날
    assert json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))["updated"] == "2026-11-24"
