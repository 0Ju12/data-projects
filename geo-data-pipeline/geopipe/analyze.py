"""지진 목록 분석: 월별 건수, 규모-빈도(구텐베르크-리히터) b값, 깊이 분포.

b값 추정
- 완전성 규모 Mc: 0.1 단위 히스토그램의 최빈값(maximum curvature) + 0.2 보정 (Woessner & Wiemer, 2005 의 관행)
- b = log10(e) / (mean(M) - (Mc - ΔM/2))  (Aki, 1965; Utsu 의 구간 보정)
- 표준오차: Shi & Bolt (1982)  σ_b = 2.30 · b² · sqrt( Σ(M - M̄)² / (n(n-1)) )
주의: USGS 목록은 지역에 따라 mb·Mw·ml 등 규모 종류가 섞여 있어 b값은 참고용 지표로만 씁니다.
"""
from __future__ import annotations

import math
from collections import Counter

DM = 0.1


def monthly_counts(events) -> list[tuple[str, int]]:
    """첫 달부터 마지막 달까지 빈 달은 0 으로 채움 (발생이 드문 지역에서 그래프가 왜곡되지 않게)"""
    c = Counter(e.time_utc[:7] for e in events)
    if not c:
        return []
    y, m = map(int, min(c).split("-"))
    ye, me = map(int, max(c).split("-"))
    out = []
    while (y, m) <= (ye, me):
        k = f"{y:04d}-{m:02d}"
        out.append((k, c.get(k, 0)))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def mag_histogram(mags: list[float], dm: float = DM) -> list[tuple[float, int]]:
    c = Counter(round(math.floor(m / dm + 1e-9) * dm, 1) for m in mags)
    return sorted(c.items())


def completeness_mc(mags: list[float], correction: float = 0.2) -> float | None:
    h = mag_histogram(mags)
    if not h:
        return None
    mode = max(h, key=lambda x: (x[1], -x[0]))[0]
    return round(mode + correction, 1)


def b_value(mags: list[float], mc: float | None = None, dm: float = DM) -> dict:
    mc = completeness_mc(mags) if mc is None else mc
    sel = [m for m in mags if mc is not None and m >= mc - 1e-9]
    n = len(sel)
    if n < 30:
        return {"mc": mc, "n": n, "b": None, "sigma": None, "a": None, "note": "Mc 이상 이벤트가 30개 미만이라 추정하지 않음"}
    mean = sum(sel) / n
    b = math.log10(math.e) / (mean - (mc - dm / 2))
    var = sum((m - mean) ** 2 for m in sel) / (n * (n - 1))
    sigma = 2.30 * b * b * math.sqrt(var)
    a = math.log10(n) + b * mc
    return {"mc": mc, "n": n, "b": round(b, 3), "sigma": round(sigma, 3), "a": round(a, 3), "note": ""}


def cumulative_fmd(mags: list[float], dm: float = DM) -> list[tuple[float, int]]:
    """규모 M 이상 누적 개수 N(≥M)"""
    if not mags:
        return []
    lo, hi = math.floor(min(mags) / dm) * dm, math.ceil(max(mags) / dm) * dm
    out, m = [], lo
    s = sorted(mags)
    while m <= hi + 1e-9:
        out.append((round(m, 1), sum(1 for x in s if x >= m - 1e-9)))
        m += dm
    return out


def depth_bins(events, edges=(0, 10, 30, 70, 150, 300, 700)) -> list[tuple[str, int]]:
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        out.append((f"{lo}–{hi} km", sum(1 for e in events if lo <= (e.depth_km or 0) < hi)))
    out.append((f"{edges[-1]}+ km", sum(1 for e in events if (e.depth_km or 0) >= edges[-1])))
    return out


def summarize(events, region: dict) -> dict:
    ev = [e for e in events if region["bbox"][0] <= e.lat <= region["bbox"][1] and region["bbox"][2] <= e.lon <= region["bbox"][3]
          and e.mag >= region["min_mag"] and e.time_utc >= region.get("since", "")]
    mags = [e.mag for e in ev]
    top = sorted(ev, key=lambda e: -e.mag)[:10]
    return {
        "region": region["name"], "n": len(ev),
        "first": min((e.time_utc for e in ev), default=None), "last": max((e.time_utc for e in ev), default=None),
        "monthly": monthly_counts(ev), "fmd": cumulative_fmd(mags), "gr": b_value(mags),
        "depth": depth_bins(ev), "mag_types": dict(Counter(e.mag_type for e in ev)),
        "largest": [{"id": e.id, "time_kst": e.time_kst, "mag": e.mag, "mag_type": e.mag_type, "depth_km": e.depth_km, "place": e.place} for e in top],
    }
