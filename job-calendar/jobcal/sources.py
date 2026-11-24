"""공고 출처별 수집 → 같은 모양의 dict 로 정리

출처는 공개 API 이면서 robots.txt 가 막지 않는 곳만 씁니다(2026-11 확인).
- 점핏: 신입(career=0) 공고 목록 API
- 카카오: careers.kakao.com 의 공개 API(/public/api)
- Greenhouse 공개 채용 API(boards-api.greenhouse.io): 회사가 외부 게시용으로 연 공고판
원티드(robots.txt 가 /api/ 를 막음)·토스(공고 목록 수집 금지) 등은 넣지 않습니다.
하루 한 번, 출처마다 몇 쪽만 받고, 공고 원문은 저장하지 않고 제목·회사·마감일·링크만 남깁니다.
"""
import json
import time
import urllib.request

from . import classify as C

UA = "job-calendar/1.0 (+https://github.com/0Ju12/data-projects; daily, low volume)"
GREENHOUSE = {   # 공고판 이름 → 화면에 보일 회사 이름
    "coupang": "쿠팡", "daangn": "당근", "krafton": "크래프톤", "moloco": "몰로코", "sendbird": "센드버드", "furiosaai": "퓨리오사AI",
}
KOREA = ("korea", "seoul", "서울", "판교", "pangyo", "성남", "busan", "부산", "대전", "daejeon", "경기", "인천", "incheon", "remote - kr")


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def day(s):
    return (s or "")[:10] or None


def jumpit_rows(payload):
    out = []
    for p in (payload.get("result") or {}).get("positions") or []:
        title = p.get("title") or ""
        cats = p.get("jobCategory") or ""
        out.append({
            "id": f"jumpit:{p['id']}", "src": "점핏", "co": p.get("companyName") or "", "title": title,
            "url": f"https://jumpit.saramin.co.kr/position/{p['id']}",
            "roles": C.roles(title, cats.replace(",", " ")), "stacks": (p.get("techStacks") or [])[:8],
            "loc": ", ".join((p.get("locations") or [])[:2]),
            "newbie": C.newbie(title, p.get("newcomer"), p.get("minCareer")),
            "start": None, "end": None if p.get("alwaysOpen") else day(p.get("closedAt")),
            "tech": True,
        })
    return out


def kakao_rows(payload):
    out = []
    for j in payload.get("jobList") or []:
        if j.get("closeFlag"):
            continue
        title = j.get("jobOfferTitle") or ""
        skills = [s.get("skillSetName") or s.get("name") for s in (j.get("skillSetList") or []) if isinstance(s, dict)]
        out.append({
            "id": f"kakao:{j['realId']}", "src": "카카오", "co": j.get("companyName") or "카카오", "title": title.replace("[공동체] ", "").strip(),
            "url": f"https://careers.kakao.com/jobs/{j['realId']}",
            "roles": C.roles(title, j.get("jobTypeName")), "stacks": [s for s in skills if s][:8], "loc": j.get("locationName") or "",
            "newbie": C.newbie(title), "start": day(j.get("regDate")), "end": day(j.get("endDate")),
            "tech": C.tech(title, j.get("jobTypeName")),
        })
    return out


def greenhouse_rows(board, payload):
    out = []
    for j in payload.get("jobs") or []:
        loc = ((j.get("location") or {}).get("name") or "")
        if not any(k in loc.lower() for k in KOREA):
            continue
        title = j.get("title") or ""
        cats = " ".join(str(m.get("value")) for m in (j.get("metadata") or []) if m.get("value") and "Category" in (m.get("name") or ""))
        out.append({
            "id": f"gh:{board}:{j['id']}", "src": "Greenhouse", "co": GREENHOUSE.get(board, j.get("company_name") or board), "title": title,
            "url": j.get("absolute_url") or "", "roles": C.roles(title, cats), "stacks": [],
            "loc": loc.split(";")[0].strip(), "newbie": C.newbie(title),
            "start": day(j.get("first_published") or j.get("updated_at")), "end": day(j.get("application_deadline")),
            "tech": C.tech(title, cats),
        })
    return out


def collect(pages=12):
    """모든 출처 → (공고 목록, 출처별 기록). 한 출처가 실패해도 나머지는 계속."""
    rows, log = [], []

    def run(name, fn):
        t0 = time.time()
        try:
            got = fn()
            rows.extend(got)
            log.append({"src": name, "n": len(got), "ok": True, "sec": round(time.time() - t0, 1)})
        except Exception as e:   # 출처 하나가 막혀도 달력은 나머지로 갱신
            log.append({"src": name, "n": 0, "ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"})

    def jumpit():
        got = []
        for page in range(1, pages + 1):
            r = jumpit_rows(get(f"https://jumpit-api.saramin.co.kr/api/positions?sort=reg_dt&highlight=false&page={page}&career=0"))
            if not r:
                break
            got += r
            time.sleep(0.8)
        return got

    def kakao():
        got = []
        for page in range(1, pages + 1):
            d = get(f"https://careers.kakao.com/public/api/job-list?skillSet=&part=TECHNOLOGY&company=ALL&employeeType=&page={page}")
            got += kakao_rows(d)
            if page >= (d.get("totalPage") or 1):
                break
            time.sleep(0.8)
        return got

    run("점핏", jumpit)
    run("카카오", kakao)
    for board in GREENHOUSE:
        run(f"Greenhouse·{GREENHOUSE[board]}", lambda b=board: greenhouse_rows(b, get(f"https://boards-api.greenhouse.io/v1/boards/{b}/jobs")))
    return rows, log
