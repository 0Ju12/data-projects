"""답 속 숫자가 조회 결과에 근거가 있는지 확인.

LLM 은 조회 결과를 문장으로 옮기면서 숫자를 틀리게 적거나 없는 숫자를 만들 수 있습니다.
답에서 숫자를 모두 뽑아, 조회 결과의 값과 맞는지 하나씩 봅니다.

숫자 하나가 '근거 있음'이 되는 경우
- 결과 값과 같음 (답에 적힌 소수 자리까지 반올림해서 비교)
- 결과 값의 단위만 바꾼 것: ÷1000 (MW→GW, m→km), ×100 (비율→%)
- 결과의 행 수
- 질문에 이미 나온 숫자 (연도·날짜·'상위 5개'의 5 처럼 조건으로 준 값)
그 밖의 숫자는 '근거 없음'으로 돌려줍니다. 합계·차이처럼 답에서 새로 계산한 값도 근거 없음이 되므로,
그런 값은 SQL 에서 계산해 결과에 넣어야 합니다.
"""
from __future__ import annotations

import re

NUM = re.compile(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])-?\d+(?:\.\d+)?")


def numbers(text: str) -> list[tuple[str, float, int]]:
    """(원문, 값, 소수 자릿수)"""
    out = []
    for m in NUM.finditer(text or ""):
        raw = m.group(0)
        clean = raw.replace(",", "")
        out.append((raw, float(clean), len(clean.split(".")[1]) if "." in clean else 0))
    return out


def result_values(result: dict) -> list[float]:
    vals = []
    for row in result.get("rows", []):
        for v in row:
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                vals.append(float(v))
            elif isinstance(v, str):
                vals += [n for _, n, _ in numbers(v)]
                vals += [float(p) for p in re.findall(r"\d+", v)]      # '2025-10-06' 의 10, 6 같은 날짜 조각
    return vals


def _match(a: float, dec: int, v: float) -> bool:
    return abs(round(v, dec) - a) <= 10 ** (-dec) * 1e-6 + 1e-9


def check(answer: str, result: dict, question: str = "") -> dict:
    vals = result_values(result)
    given = {n for _, n, _ in numbers(question)} | {float(p) for p in re.findall(r"\d+", question or "")}
    supported, unsupported = [], []
    for raw, a, dec in numbers(answer):
        how = None
        if any(_match(a, dec, v) for v in vals):
            how = "결과 값"
        elif any(_match(a, dec, v / 1000) for v in vals):
            how = "결과 값 ÷ 1000"
        elif any(_match(a, dec, v * 100) for v in vals):
            how = "결과 값 × 100"
        elif dec == 0 and a == result.get("row_count") and not result.get("truncated"):
            how = "행 수"
        elif a in given:
            how = "질문에 나온 값"
        (supported if how else unsupported).append({"number": raw, "basis": how} if how else {"number": raw})
    return {"ok": not unsupported, "checked": len(supported) + len(unsupported), "supported": supported, "unsupported": unsupported}
