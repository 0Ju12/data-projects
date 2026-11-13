"""가상자산 일봉과 환율 수집 (모두 키 없는 공개 API)

- 업비트 원화 마켓 일봉 (하루 경계 = UTC 0시)
- 코인베이스 달러 마켓 일봉 (하루 경계 = UTC 0시)
- 환율 USD→KRW·JPY·EUR (Frankfurter, 유럽중앙은행 기준환율 — 영업일에만 값이 있음)

하루 경계가 같은 두 거래소만 묶었습니다. 빗썸 일봉은 한국 시간 0시에 끊겨(UTC 15시) 같은 '하루'가 아니므로 넣지 않았습니다.
아직 끝나지 않은 오늘(UTC)의 봉은 값이 계속 바뀌므로 저장하지 않습니다.
"""
from __future__ import annotations

import csv
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .jobs import http_json

ROOT = Path(__file__).resolve().parent.parent.parent
CANDLES = ROOT / "data" / "market_candles.csv"
FX = ROOT / "data" / "fx_rates.csv"
ASSETS = ["BTC", "ETH", "XRP", "SOL"]
QUOTES = ["KRW", "JPY", "EUR"]
C_FIELDS = ["exchange", "asset", "quote", "day_utc", "open", "high", "low", "close", "volume"]
F_FIELDS = ["day", "base", "quote", "rate"]
BACKFILL_DAYS = 730
OVERLAP_DAYS = 7          # 최근 며칠은 다시 받아 바꿔 넣습니다 (늦게 고쳐진 봉·놓친 날 메우기)


def _load(path: Path, key) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {key(r): r for r in csv.DictReader(f)}


def _save(rows: dict, path: Path, fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])
    os.replace(tmp, path)


def _num(x) -> str:
    """부동소수 표기 차이로 파일이 달라지지 않도록 고정 형식으로"""
    return format(float(x), ".10g")


def upbit_days(asset: str, start: date, end: date, get=http_json, pause=0.15) -> list[dict]:
    """start ~ end(포함) 의 일봉. 최신부터 200개씩 거슬러 올라갑니다."""
    out, to = {}, end + timedelta(days=1)
    while to > start:
        data = get(f"https://api.upbit.com/v1/candles/days?market=KRW-{asset}&count=200&to={to.isoformat()}%2000:00:00")
        if not data:
            break
        for c in data:
            d = c["candle_date_time_utc"][:10]
            if start.isoformat() <= d <= end.isoformat():
                out[d] = {"exchange": "upbit", "asset": asset, "quote": "KRW", "day_utc": d, "open": _num(c["opening_price"]),
                          "high": _num(c["high_price"]), "low": _num(c["low_price"]), "close": _num(c["trade_price"]),
                          "volume": _num(c["candle_acc_trade_volume"])}
        oldest = date.fromisoformat(min(c["candle_date_time_utc"][:10] for c in data))
        if oldest >= to or len(data) < 200:
            break
        to = oldest
        time.sleep(pause)
    return list(out.values())


def coinbase_days(asset: str, start: date, end: date, get=http_json, pause=0.2) -> list[dict]:
    """코인베이스는 한 번에 300개까지. 응답 한 줄 = [시각, 저가, 고가, 시가, 종가, 거래량]"""
    out, a = {}, start
    while a <= end:
        b = min(a + timedelta(days=299), end)
        data = get(f"https://api.exchange.coinbase.com/products/{asset}-USD/candles?granularity=86400"
                   f"&start={a.isoformat()}T00:00:00Z&end={b.isoformat()}T00:00:00Z")
        for t, lo, hi, op, cl, vol in data or []:
            d = datetime.fromtimestamp(int(t), tz=timezone.utc).date().isoformat()
            if start.isoformat() <= d <= end.isoformat():
                out[d] = {"exchange": "coinbase", "asset": asset, "quote": "USD", "day_utc": d, "open": _num(op), "high": _num(hi),
                          "low": _num(lo), "close": _num(cl), "volume": _num(vol)}
        a = b + timedelta(days=1)
        if a <= end:
            time.sleep(pause)
    return list(out.values())


def fx_days(start: date, end: date, get=http_json) -> list[dict]:
    data = get(f"https://api.frankfurter.dev/v1/{start.isoformat()}..{end.isoformat()}?base=USD&symbols={','.join(QUOTES)}")
    return [{"day": d, "base": "USD", "quote": q, "rate": _num(r)} for d, m in (data.get("rates") or {}).items() for q, r in m.items()]


def collect(today: str | None = None, candles_path: Path = CANDLES, fx_path: Path = FX, get=http_json, pause=0.15,
            backfill_days: int = BACKFILL_DAYS) -> dict:
    """끝난 날(어제 UTC)까지 받습니다. 처음에는 backfill_days 만큼, 그 뒤에는 마지막으로 가진 날의 OVERLAP_DAYS 전부터."""
    today_d = date.fromisoformat(today) if today else datetime.now(timezone.utc).date()
    end = today_d - timedelta(days=1)
    candles = _load(candles_path, lambda r: (r["exchange"], r["asset"], r["day_utc"]))
    fx = _load(fx_path, lambda r: (r["day"], r["quote"]))
    stats = {"end": end.isoformat(), "candles_new": 0, "candles_changed": 0, "fx_new": 0, "errors": []}
    for exchange, fetch in (("upbit", upbit_days), ("coinbase", coinbase_days)):
        for asset in ASSETS:
            have = [k[2] for k in candles if k[0] == exchange and k[1] == asset]
            start = max(date.fromisoformat(max(have)) - timedelta(days=OVERLAP_DAYS), end - timedelta(days=backfill_days)) if have \
                else end - timedelta(days=backfill_days)
            try:
                rows = fetch(asset, start, end, get, pause)
            except Exception as e:
                stats["errors"].append(f"{exchange}:{asset}:{type(e).__name__}")
                continue
            for r in rows:
                k = (r["exchange"], r["asset"], r["day_utc"])
                if k not in candles:
                    stats["candles_new"] += 1
                elif any(candles[k][f] != r[f] for f in ("open", "high", "low", "close", "volume")):
                    stats["candles_changed"] += 1
                candles[k] = r
    have = [k[0] for k in fx]
    start = max(date.fromisoformat(max(have)) - timedelta(days=OVERLAP_DAYS), end - timedelta(days=backfill_days)) if have \
        else end - timedelta(days=backfill_days)
    try:
        for r in fx_days(start, end, get):
            if r["day"] <= end.isoformat():
                k = (r["day"], r["quote"])
                stats["fx_new"] += k not in fx
                fx[k] = r
    except Exception as e:
        stats["errors"].append(f"fx:{type(e).__name__}")
    _save(candles, candles_path, C_FIELDS)
    _save(fx, fx_path, F_FIELDS)
    stats["candles_total"], stats["fx_total"] = len(candles), len(fx)
    return stats
