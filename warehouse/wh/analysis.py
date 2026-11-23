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


# ── 일사량과 한낮 수요 ────────────────────────────────────────────────
# 수요 = 달별 절편 + a × 새벽 최저 + b × (일사량 / 100) + c × max(기온 − 24, 0) + d × max(16 − 기온, 0)
# 같은 달끼리 비교(달별 절편), 그날의 기본 수요 수준(새벽 최저), 냉난방(기온)을 함께 넣고 b 를 봅니다.
# 같은 식을 해가 진 20~23시 수요에 맞춘 값은 대조군입니다. 태양광 때문이라면 b 가 0 근처여야 합니다.

COOL_C, HEAT_C = 24.0, 16.0


def _solve(a: list[list[float]], b: list[float]) -> list[float] | None:
    """n×n 가우스 소거 (부분 피벗). 특이 행렬이면 None."""
    n = len(b)
    m = [row[:] + [v] for row, v in zip(a, b)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(m[r][i]))
        if abs(m[p][i]) < 1e-9:
            return None
        m[i], m[p] = m[p], m[i]
        piv = m[i][i]
        m[i] = [x / piv for x in m[i]]
        for r in range(n):
            if r != i and m[r][i]:
                f = m[r][i]
                m[r] = [x - f * y for x, y in zip(m[r], m[i])]
    return [m[i][n] for i in range(n)]


def ols(xs: list[list[float]], ys: list[float]) -> dict | None:
    """최소제곱 계수, 표준오차, R². 외부 패키지 없이 정규방정식으로."""
    n, k = len(ys), len(xs[0]) if xs else 0
    if n <= k + 2:
        return None
    ata = [[sum(x[i] * x[j] for x in xs) for j in range(k)] for i in range(k)]
    aty = [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(k)]
    beta = _solve(ata, aty)
    if beta is None:
        return None
    res = [y - sum(b * xi for b, xi in zip(beta, x)) for x, y in zip(xs, ys)]
    sse = sum(r * r for r in res)
    mean = sum(ys) / n
    sst = sum((y - mean) ** 2 for y in ys)
    s2 = sse / (n - k)
    se = []
    for j in range(k):                       # (XᵀX)⁻¹ 의 대각 원소만 필요 → 단위 벡터로 j 번째 열을 풂
        col = _solve(ata, [1.0 if i == j else 0.0 for i in range(k)])
        se.append((s2 * col[j]) ** 0.5 if col and col[j] > 0 else None)
    return {"beta": beta, "se": se, "r2": 1 - sse / sst if sst else None, "n": n}


def _design(rows, months, temp_key, rad_scale=100.0):
    xs = []
    for r in rows:
        dummies = [1.0 if r["month"] == m else 0.0 for m in months]
        t = r[temp_key]
        xs.append(dummies + [r["night_min_mw"], r["midday_rad"] / rad_scale, max(t - COOL_C, 0.0), max(HEAT_C - t, 0.0)])
    return xs


def fit_solar(rows: list[dict], target: str = "midday_mw", temp_key: str = "midday_temp") -> dict | None:
    """일사량 100 W/m² 당 수요 변화(MW)와 표준오차. rows 는 ana_solar_daily 의 행(dict)."""
    rows = [r for r in rows if None not in (r.get(target), r.get(temp_key), r.get("midday_rad"), r.get("night_min_mw"))]
    months = sorted({r["month"] for r in rows})
    if len(rows) < len(months) + 10:
        return None
    xs = _design(rows, months, temp_key)
    k = len(months) + 1                       # 달별 절편 다음이 새벽 최저, 그 다음이 일사량
    keep = [j for j in range(len(xs[0])) if j <= k or any(x[j] for x in xs)]   # 겨울의 냉방항·여름의 난방항처럼 모두 0인 열은 뺌
    fit = ols([[x[j] for j in keep] for x in xs], [float(r[target]) for r in rows])
    if fit is None:
        return None
    b, se = fit["beta"][k], fit["se"][k]
    return {"mw_per_100w": round(b), "se": round(se) if se else None,
            "ci95": [round(b - 1.96 * se), round(b + 1.96 * se)] if se else None,
            "r2": round(fit["r2"], 3) if fit["r2"] is not None else None, "days": fit["n"]}


SEASONS = {"winter": (12, 1, 2), "spring": (3, 4, 5), "summer": (6, 7, 8), "autumn": (9, 10, 11)}


def solar_analysis(con) -> dict:
    cols = ["demand_date", "month", "midday_mw", "night_min_mw", "evening_mw", "midday_temp", "evening_temp", "midday_rad", "midday_vs_night"]
    rows = [dict(zip(cols, r)) for r in con.execute(f"select {', '.join(cols)} from ana_solar_daily order by demand_date").fetchall()]
    for r in rows:
        for c in cols[1:]:
            r[c] = float(r[c]) if r[c] is not None else None
    out = {"midday": fit_solar(rows), "evening": fit_solar(rows, "evening_mw", "evening_temp"),
           "seasons": {s: fit_solar([r for r in rows if r["month"] in ms]) for s, ms in SEASONS.items()},
           "cool_above": COOL_C, "heat_below": HEAT_C}
    # 같은 달 안 맑음(상위 3분의 1)과 흐림(하위 3분의 1)의 평균 일사량 차이 → 계수로 환산한 '전형적인 차이'
    t = con.execute("""select avg(case when sun_tercile = 3 then midday_rad end) - avg(case when sun_tercile = 1 then midday_rad end)
                       from ana_solar_terciles""").fetchone()[0]
    if out["midday"] and t:
        out["sunny_cloudy_rad_gap"] = round(float(t))
        out["sunny_cloudy_mw"] = round(out["midday"]["mw_per_100w"] * float(t) / 100)
    out["points"] = [[r["midday_rad"], r["midday_vs_night"], int(r["month"])] for r in rows if r["midday_rad"] is not None]
    return out
