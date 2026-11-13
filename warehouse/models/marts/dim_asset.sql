-- 자산 차원: 어느 거래소에서 며칠부터 며칠까지 있는지
select
    asset,
    count(distinct exchange)            as exchanges,
    min(day_utc)                        as first_day,
    max(day_utc)                        as last_day,
    count(*) filter (where exchange = 'upbit')    as upbit_days,
    count(*) filter (where exchange = 'coinbase') as coinbase_days
from {{ ref('stg_candles') }}
group by 1
