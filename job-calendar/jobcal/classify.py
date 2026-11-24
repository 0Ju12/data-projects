"""공고 제목·분류를 직무 9가지(+기타)로 나누고, 신입 여부를 추정합니다.

여러 출처의 분류 체계가 서로 달라서(점핏 jobCategory, 카카오 jobType, Greenhouse metadata) 제목과 분류 글자를
같은 규칙으로 읽습니다. 한 공고가 여러 직무에 걸칠 수 있습니다(예: '데이터 플랫폼 백엔드').
"""
import re

ROLES = ["백엔드", "프론트엔드", "모바일", "데이터·AI", "인프라·클라우드", "보안", "임베디드·하드웨어", "QA", "게임"]
OTHER = "기타"

_A = r"(?<![A-Za-z])"   # 영어 낱말 경계 (한글 바로 옆도 경계로 봄)
_Z = r"(?![A-Za-z])"
RULES = [
    ("데이터·AI", rf"데이터|머신\s?러닝|딥\s?러닝|인공지능|추천\s?시스템|자연어|컴퓨터\s?비전|{_A}(data|ML|MLOps|LLM|AI|NLP|analyst|analytics|scientist|machine learning|deep learning|vision|recommend\w*){_Z}"),
    ("백엔드", rf"백엔드|서버|플랫폼\s?개발|풀\s?스택|{_A}(back-?end|server|API|Java|Spring|Kotlin|Node\.?js|Django|full-?stack|platform engineer\w*){_Z}"),
    ("프론트엔드", rf"프론트|웹\s?개발|웹\s?퍼블리|퍼블리셔|{_A}(front-?end|React|Vue|web developer|web engineer|full-?stack){_Z}"),
    ("모바일", rf"안드로이드|모바일|앱\s?개발|{_A}(android|iOS|mobile|flutter|react native|swift){_Z}"),
    ("인프라·클라우드", rf"인프라|클라우드|네트워크|시스템\s?엔지니어|데브옵스|{_A}(devops|SRE|infra\w*|cloud|kubernetes|k8s|DBA|network|IT infra|reliability){_Z}"),
    ("보안", rf"보안|침해|취약점|{_A}(security|secops|offensive|penetration){_Z}"),
    ("임베디드·하드웨어", rf"임베디드|펌웨어|하드웨어|반도체|회로|컴파일러|{_A}(embedded|firmware|hardware|FPGA|RTL|NPU|SoC|compiler|ASIC|kernel|driver){_Z}"),
    ("QA", rf"{_A}(QA|QE|SDET|test\w*){_Z}|테스트|품질"),
    ("게임", rf"게임|언리얼|유니티|클라이언트\s?개발|{_A}(game|unreal|unity|client programmer|gameplay){_Z}"),
]
_COMPILED = [(r, re.compile(p, re.I)) for r, p in RULES]

# 개발 직군이 아닌 공고 (기획·사업·디자인 등) — '기타'로 남기되 화면 기본값에서는 숨김
NON_TECH = re.compile(r"마케팅|영업|사업\s?개발|재무|회계|인사|HR|법무|디자이너|아트|사운드|운영\s?매니저|CS\s|고객|Business Development|Marketing|Sales|Finance|Legal|Recruit|Art|Sound|Designer", re.I)

NEWBIE = re.compile(rf"신입|인턴|채용\s?연계|주니어|경력\s?무관|경력\s?0|0\s?년|졸업\s?예정|{_A}(intern\w*|new grad\w*|junior|entry[- ]level|graduate){_Z}", re.I)
SENIOR = re.compile(rf"경력|\d+\s?년\s?이상|시니어|리드|팀장|파트\s?리더|{_A}(senior|sr\.|lead|staff|principal|head|manager|director){_Z}", re.I)


def roles(*texts):
    """제목·분류 글자들 → 직무 목록 (규칙 순서대로, 겹치면 여러 개)"""
    t = " ".join(x for x in texts if x)
    found = [r for r, rx in _COMPILED if rx.search(t)]
    return found or [OTHER]


def newbie(title, flag=None, min_career=None):
    """신입 지원 가능 여부: True(신입·인턴), False(경력), None(공고에 표시 없음)"""
    if flag is True or min_career == 0:
        return True
    if NEWBIE.search(title or ""):
        return True
    if flag is False or (min_career or 0) > 0 or SENIOR.search(title or ""):
        return False
    return None


ENGINEER = re.compile(rf"개발|엔지니어|연구원|분석가|{_A}(engineer\w*|developer|scientist|analyst|researcher|programmer|SRE|QA){_Z}", re.I)


def tech(title, *cats):
    """개발·데이터 직군인지: 사업·마케팅 등 분류라도 제목에 엔지니어·개발이 있으면 개발 직군으로 봄"""
    if ENGINEER.search(title or ""):
        return True
    return not NON_TECH.search(" ".join([title or "", *[c for c in cats if c]])) and roles(title) != [OTHER]
