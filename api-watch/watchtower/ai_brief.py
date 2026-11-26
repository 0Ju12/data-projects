"""One daily source-grounded learning note. No LLM/API key or model download required."""

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone as djtime

from .models import DailyBrief

WATCH = [
    {
        "repo": "huggingface/transformers",
        "name": "Transformers",
        "what": "여러 모델의 토크나이저·모델 로딩·추론 인터페이스를 제공하는 라이브러리입니다.",
        "why": "POSPEAK의 모델 실험과 VQA 작업에서 모델·토크나이저·버전 호환성을 확인하는 데 연결할 수 있습니다.",
        "flow": ["모델·토크나이저 선택", "입력 전처리", "모델 추론", "출력·평가"],
        "limits": [
            "라이브러리 업데이트와 새 모델의 성능 개선은 같은 주장이 아닙니다.",
            "지원 모델·설치 조건·라이선스는 해당 버전 문서에서 확인해야 합니다.",
        ],
        "question": "라이브러리 버전을 바꿨을 때 동일 입력의 결과가 달라졌는지 어떻게 검증할까요?",
    },
    {
        "repo": "vllm-project/vllm",
        "name": "vLLM",
        "what": "언어 모델 추론을 서버로 제공할 때 처리량과 메모리 사용을 다루는 추론 엔진입니다.",
        "why": "모델을 학습한 뒤 API 서비스로 제공하는 과정, 동시 요청·지연·메모리 조건을 비교하는 실험으로 확장할 수 있습니다.",
        "flow": ["요청 수신", "스케줄링·배치", "모델 추론", "토큰 응답"],
        "limits": [
            "실제 GPU·모델·배치 조건 없이 속도 개선 수치를 일반화할 수 없습니다.",
            "학습 프레임워크와 추론 서빙 엔진의 역할을 구분해야 합니다.",
        ],
        "question": "평균 응답 시간과 첫 토큰 지연, 처리량은 각각 어떤 의미가 있을까요?",
    },
    {
        "repo": "ollama/ollama",
        "name": "Ollama",
        "what": "로컬 환경에서 모델을 내려받고 실행하며 API로 호출할 수 있게 돕는 도구입니다.",
        "why": "개인 RAG 기능에서 외부 모델 API와 로컬 모델의 품질·비용·실행 환경을 비교할 수 있습니다.",
        "flow": ["모델 선택", "로컬 실행", "API 호출", "RAG·서비스 연결"],
        "limits": [
            "모델 파일 크기와 하드웨어 요구 사항을 먼저 확인해야 합니다.",
            "로컬에서 실행된다는 사실이 모델 품질이나 데이터 보안을 자동 보장하지는 않습니다.",
        ],
        "question": "외부 API와 로컬 모델을 같은 질문 세트로 공정하게 비교하려면 무엇을 고정해야 할까요?",
    },
    {
        "repo": "ggml-org/llama.cpp",
        "name": "llama.cpp",
        "what": "여러 하드웨어 환경에서 언어 모델 추론을 실행하는 C/C++ 기반 프로젝트입니다.",
        "why": "양자화·모델 크기·실행 환경이 지연과 품질에 미치는 영향을 직접 비교하는 학습에 적합합니다.",
        "flow": ["모델 형식 확인", "양자화 조건 선택", "추론 실행", "품질·자원 비교"],
        "limits": [
            "양자화 비트 수만으로 품질이나 속도를 예측할 수 없습니다.",
            "지원 하드웨어와 모델 형식은 릴리스 원문에서 확인해야 합니다.",
        ],
        "question": "메모리 사용량을 줄였을 때 어떤 질문 유형에서 품질 회귀가 생겼는지 어떻게 찾을까요?",
    },
    {
        "repo": "langchain-ai/langgraph",
        "name": "LangGraph",
        "what": "상태와 분기를 가진 LLM 작업 흐름을 그래프로 구성하는 도구입니다.",
        "why": "국보 RAG에서 검색·생성·인용 확인·실패 대응을 분리한 경험과 연결해 이해할 수 있습니다.",
        "flow": ["상태 입력", "검색·도구 노드", "검증·분기", "최종 응답"],
        "limits": [
            "그래프를 썼다는 이유만으로 에이전트의 정확성이 높아지는 것은 아닙니다.",
            "반복 횟수·실패 경로·비용·권한을 별도로 평가해야 합니다.",
        ],
        "question": "검색 결과가 부족할 때 재검색과 답변 거절 중 어느 경로를 선택할까요?",
    },
]


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlparse

        if urlparse(newurl).netloc != urlparse(req.full_url).netloc:
            raise urllib.error.URLError("cross-host redirect blocked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def get_json(url):
    headers = {"User-Agent": "0Ju12-AI-Daily/1.0", "Accept": "application/json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.build_opener(SameHostRedirect()).open(request, timeout=10) as r:
        raw = r.read(1500000)
        return json.loads(raw)


def clean(text):
    text = re.sub(r"```.*?```", "", text or "", flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"!\[[^]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def make_daily(fetcher=get_json):
    now = djtime.now()
    day = now.astimezone(ZoneInfo("Asia/Seoul")).date()
    previous = DailyBrief.objects.filter(date=day).first()
    if previous:
        return previous, False
    used = set(DailyBrief.objects.values_list("item_id", flat=True))
    candidates = []
    errors = []
    for tool in WATCH:
        try:
            releases = fetcher("https://api.github.com/repos/" + tool["repo"] + "/releases?per_page=4")
            if not isinstance(releases, list):
                raise ValueError("not release list")
            for r in releases:
                published = r.get("published_at")
                url = r.get("html_url", "")
                if (
                    r.get("draft")
                    or r.get("prerelease")
                    or not published
                    or not url.startswith("https://github.com/" + tool["repo"] + "/releases/")
                ):
                    continue
                moment = datetime.fromisoformat(published.replace("Z", "+00:00"))
                item = tool["repo"] + ":" + str(r.get("id") or r.get("tag_name"))
                if now - timedelta(days=30) <= moment <= now and item not in used:
                    candidates.append((published, tool, r, item))
        except Exception as e:
            errors.append({"source": tool["repo"], "error": type(e).__name__})
    candidates.sort(key=lambda c: c[0], reverse=True)
    models = []
    try:
        for m in fetcher("https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=20&full=true"):
            mid = m.get("id", "")
            author = mid.split("/")[0]
            if author not in {
                "Qwen",
                "google",
                "meta-llama",
                "mistralai",
                "HuggingFaceTB",
                "deepseek-ai",
                "MiniMaxAI",
            } or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", mid):
                continue
            modified = m.get("lastModified")
            if not modified:
                continue
            moment = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            if now - timedelta(days=30) <= moment <= now and "model:" + mid not in used:
                models.append(m)
    except Exception as e:
        errors.append({"source": "Hugging Face models", "error": type(e).__name__})
    source_extra = None
    if models and (day.toordinal() % 2 == 0 or not candidates):
        m = models[0]
        mid = m["id"]
        pipeline = m.get("pipeline_tag", "원문 확인 필요")
        card = m.get("cardData") or {}
        tool = {
            "name": mid,
            "repo": mid,
            "what": "Hugging Face에 공개된 모델 저장소입니다. 메타데이터의 작업 유형은 "
            + pipeline
            + "이며, 실제 지원 입력·출력과 사용 조건은 모델 카드에서 확인해야 합니다.",
            "why": "본인의 VQA·교정 모델·RAG 실험에서 같은 평가 입력과 기준선을 고정해 비교하는 후보로 검토할 수 있습니다. 최근 수정이나 다운로드 수만으로 더 우수하다고 판단하지 않습니다.",
            "flow": ["모델 카드·라이선스 확인", "작업·입출력 확인", "기준선과 평가 설계", "자원·오류 유형 비교"],
            "limits": [
                "저장소 수정일은 신규 모델의 최초 발표일과 다를 수 있습니다.",
                "메타데이터만으로 성능·메모리·라이선스 적합성을 검증하지 않았습니다.",
            ],
            "question": "이 모델을 내 프로젝트의 기준선과 비교할 때 데이터·프롬프트·평가 조건을 어떻게 고정할까요?",
        }
        kind = "model"
        label = "공개 모델 저장소 업데이트 · 최초 발표일과 구분"
        title = mid
        item = "model:" + mid
        url = "https://huggingface.co/" + mid
        published = None
        version = ""
        excerpt = "모델을 다운로드하거나 실행하지 않고 공개 메타데이터를 읽어 구성한 학습 노트입니다."
        facts = [
            {"label": "모델 ID", "value": mid},
            {"label": "작업 유형", "value": pipeline},
            {"label": "저장소 최근 수정일", "value": m["lastModified"]},
            {"label": "라이브러리", "value": m.get("library_name") or "명시 없음"},
            {"label": "라이선스", "value": str(card.get("license") or "모델 카드 원문 확인 필요")},
            {"label": "접근 제한", "value": str(m.get("gated", False))},
        ]
        source_extra = {"title": "모델 메타데이터 원문", "url": "https://huggingface.co/api/models/" + mid}
    elif candidates:
        published, tool, r, item = candidates[0]
        kind = "release"
        label = "관심 저장소의 공식 릴리스"
        title = tool["name"] + " · " + clean(r.get("name") or r.get("tag_name"))[:100]
        url = r["html_url"]
        version = r.get("tag_name", "")
        excerpt = clean(r.get("body"))[:520]
        facts = [
            {"label": "공식 발표일", "value": published},
            {"label": "버전", "value": version},
            {"label": "저장소", "value": tool["repo"]},
        ]
    else:
        tool = WATCH[day.toordinal() % len(WATCH)]
        kind = "reading"
        label = "기존 기술 학습 · 새 발표로 표시하지 않음"
        title = tool["name"] + " · 기본 구조와 검증 방법"
        item = "reading:" + tool["repo"] + ":" + day.isoformat()
        url = "https://github.com/" + tool["repo"]
        published = None
        version = ""
        excerpt = "최근 30일의 아직 소개하지 않은 공식 안정 릴리스를 확인하지 못해 기초 학습 자료를 제공합니다."
        facts = [{"label": "자료 범위", "value": "관심 저장소 5개 · 최근 30일의 안정 릴리스"}]
    payload = {
        "date": day.isoformat(),
        "item_id": item,
        "created_at": now.isoformat(),
        "kind": kind,
        "label": label,
        "title": title,
        "technology": tool["name"],
        "official_published_at": published,
        "collected_at": now.isoformat(),
        "what": tool["what"],
        "why_for_you": tool["why"],
        "flow": tool["flow"],
        "release_excerpt": excerpt,
        "facts": facts,
        "limits": tool["limits"],
        "question": tool["question"],
        "sources": [
            {"title": "모델 카드" if kind == "model" else "공식 릴리스 또는 프로젝트 원문", "url": url},
            source_extra or {"title": "공식 저장소", "url": "https://github.com/" + tool["repo"]},
        ],
        "exercise": {
            "title": "오늘의 10분 실습 · 모델 다운로드 없이 시작",
            "steps": [
                "공식 원문에서 지원 환경·호환성 변경 한 가지를 찾습니다.",
                "내 프로젝트에 적용할 가설과 비교 기준을 한 문장씩 적습니다.",
                "변경 전후에 같은 입력을 넣는 평가 항목 3개를 작성합니다.",
            ],
            "output": "확인한 사실 1개 · 아직 확인하지 못한 점 1개 · 다음 실험 1개",
        },
        "composition": "공식 메타데이터 + 사전 작성한 한국어 기술 설명으로 자동 구성합니다. LLM이 릴리스를 검증하거나 모델 성능을 평가한 결과가 아닙니다.",
        "fetch_errors": errors,
        "notification": "대시보드에서 하루 1개 갱신 · 메시지·이메일 자동 발송 없음",
    }
    record, created = DailyBrief.objects.get_or_create(
        date=day, defaults={"item_id": item, "created_at": now, "payload": payload}
    )
    return record, created
