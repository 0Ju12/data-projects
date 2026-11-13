-- 거래소 일봉 (업비트 원화 · 코인베이스 달러). 하루 경계는 둘 다 UTC 0시
select
    exchange,
    asset,
    quote,
    cast(day_utc as date)   as day_utc,
    cast(open as double)    as open,
    cast(high as double)    as high,
    cast(low as double)     as low,
    cast(close as double)   as close,
    cast(volume as double)  as volume
from read_csv('{{ var("candles_csv") }}', header = true, all_varchar = true)
