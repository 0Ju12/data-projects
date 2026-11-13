-- 일 × 자산: 업비트 원화 종가와, 코인베이스 달러 종가를 그날 환율로 원화로 바꾼 값의 차이 (흔히 '김치 프리미엄')
-- premium_pct > 0 이면 원화 시장이 더 비쌉니다. 환율이 주말 값(is_fx_filled)이면 금요일 환율로 계산한 것입니다.
select
    u.day_utc,
    u.asset,
    u.close                                         as upbit_close_krw,
    c.close                                         as coinbase_close_usd,
    f.rate                                          as usdkrw,
    f.is_filled                                     as is_fx_filled,
    f.stale_days                                    as fx_stale_days,
    round(c.close * f.rate, 2)                      as coinbase_close_krw,
    round((u.close / (c.close * f.rate) - 1) * 100, 4) as premium_pct,
    u.volume                                        as upbit_volume,
    c.volume                                        as coinbase_volume
from {{ ref('stg_candles') }} u
join {{ ref('stg_candles') }} c on c.exchange = 'coinbase' and c.asset = u.asset and c.day_utc = u.day_utc
join {{ ref('int_fx_daily') }} f on f.day = u.day_utc and f.quote = 'KRW'
where u.exchange = 'upbit' and f.rate is not null
