-- 업비트에 봉이 있는 날은 모두 프리미엄이 계산돼야 합니다 (코인베이스 봉이나 환율이 빠지면 조인에서 조용히 사라지므로 확인)
select u.asset, u.day_utc
from {{ ref('stg_candles') }} u
left join {{ ref('fct_krw_premium_daily') }} p on p.asset = u.asset and p.day_utc = u.day_utc
where u.exchange = 'upbit' and p.day_utc is null
