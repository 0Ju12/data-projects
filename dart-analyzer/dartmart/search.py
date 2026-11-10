"""공시 문단 검색 (LLM 없음): 한국어는 띄어쓰기·조사 때문에 단어 단위가 잘 안 맞아 '글자 2-gram' BM25 를 씁니다.

답은 만들어 내지 않고, 점수가 높은 원문 문단을 출처(보고서·절)와 함께 그대로 돌려줍니다.
점수가 기준 미만이면 "근거 없음"을 돌려줘 엉뚱한 문단을 답처럼 보이지 않게 합니다.
"""
from __future__ import annotations

import math
import re
from collections import Counter


def tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[0-9A-Za-z]+|[가-힣]+", text.lower()):
        if re.fullmatch(r"[가-힣]+", w):
            out += [w[i:i + 2] for i in range(len(w) - 1)] or [w]
        else:
            out.append(w)
    return out


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(tokens(d)) for d in docs]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 0
        df = Counter()
        for t in self.tf:
            df.update(t.keys())
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokens(query)
        out = []
        for tf, L in zip(self.tf, self.len):
            s = 0.0
            for w in q:
                if w in tf:
                    f = tf[w]
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * L / (self.avg or 1)))
            out.append(s)
        return out


def search(paragraphs: list[dict], query: str, k: int = 3, min_score: float | None = None) -> list[dict]:
    """paragraphs: [{text, section, report_nm, rcept_no, ...}] → 점수 순 상위 k (근거 없음이면 빈 목록)"""
    if not paragraphs:
        return []
    bm = BM25([p["text"] for p in paragraphs])
    sc = bm.scores(query)
    qn = len(set(tokens(query))) or 1
    floor = min_score if min_score is not None else 0.8 * qn       # 질의 토큰 수에 비례한 최소 점수
    ranked = sorted(zip(sc, paragraphs), key=lambda x: -x[0])
    return [dict(p, score=round(s, 2)) for s, p in ranked[:k] if s >= floor]
