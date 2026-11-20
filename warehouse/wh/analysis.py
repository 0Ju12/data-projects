"""수요-기온 관계를 '난방 구간 + 냉방 구간' 두 직선으로 맞추기 (집계는 dbt, 모형 적합만 여기서).

    수요 = 기본 + 난방 기울기 × max(난방 기준 − 기온, 0) + 냉방 기울기 × max(기온 − 냉방 기준, 0)

두 기준 기온은 0.5°C 간격으로 모두 대 보고 오차 제곱합이 가장 작은 쌍을 고릅니다.
외부 패키지 없이 3×3 정규방정식을 직접 풉니다 (CI 의 의존성을 dbt 하나로 유지하려고).
"""
from __future__ import annotations


def _solve3(a: list[list[float]], b: list[float]) -> list[float] | None:
    """가우스 소거 (부분 피벗). 특이 행렬이면 None."""
    m = [row[:] + [v] for row, v in zip(a, b)]
    for i in range(3):
        p = max(range(i, 3), key=lambda r: abs(m[r][i]))
        if abs(m[p][i]) < 1e-9:
            return None
        m[i], m[p] = m[p], m[i]
        for r in range(3):
            if r != i:
                f = m[r][i] / m[i][i]
                m[r] = [x - f * y for x, y in zip(m[r], m[i])]
    return [m[i][3] / m[i][i] for i in range(3)]


def _fit(temps, ys, th, tc):
    xs = [(1.0, max(th - t, 0.0), max(t - tc, 0.0)) for t in temps]
    ata = [[sum(x[i] * x[j] for x in xs) for j in range(3)] for i in range(3)]
    aty = [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(3)]
    beta = _solve3(ata, aty)
    if beta is None:
        return None
    sse = sum((sum(b * xi for b, xi in zip(beta, x)) - y) ** 2 for x, y in zip(xs, ys))
    return beta, sse


def fit_temperature(temps: list[float], ys: list[float], heat_range=(8.0, 18.0), cool_max=24.0, step=0.5) -> dict | None:
    """가장 잘 맞는 (난방 기준, 냉방 기준)과 기울기·설명력(R²). 자료가 모자라면 None."""
    n = len(ys)
    if n < 20:
        return None
    mean = sum(ys) / n
    sst = sum((y - mean) ** 2 for y in ys)
    best = None
    th = heat_range[0]
    while th <= heat_range[1] + 1e-9:
        tc = th
        while tc <= cool_max + 1e-9:
            r = _fit(temps, ys, th, tc)
            # 기울기는 물리적으로 0 이상이어야 의미가 있음 (난방·냉방 모두 기온에서 멀어질수록 수요 증가)
            if r and r[0][1] >= 0 and r[0][2] >= 0 and (best is None or r[1] < best[2]):
                best = (th, tc, r[1], r[0])
            tc += step
        th += step
    if best is None:
        return None
    th, tc, sse, (base, heat, cool) = best
    return {"heat_below": th, "cool_above": tc, "base_mw": round(base), "heat_mw_per_c": round(heat),
            "cool_mw_per_c": round(cool), "r2": round(1 - sse / sst, 3) if sst else None, "days": n}


def temperature_analysis(con) -> dict:
    """평일만 써서 일평균·일최대 수요 각각 적합 (쉬는 날은 수요 수준이 달라 섞지 않음)."""
    rows = con.execute("select temp_mean, mean_mw, peak_mw from fct_demand_daily where day_type = 'weekday' order by demand_date").fetchall()
    t = [float(r[0]) for r in rows]
    out = {"mean": fit_temperature(t, [float(r[1]) for r in rows]), "peak": fit_temperature(t, [float(r[2]) for r in rows])}
    out["points"] = [[round(a, 2), round(b), c] for a, b, c in rows]
    return out
