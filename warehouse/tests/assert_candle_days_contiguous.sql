-- 거래소는 쉬는 날이 없으므로, 자산마다 날짜가 하루도 빠지지 않아야 합니다 (수집이 며칠 멈췄다 돌면 여기서 드러남)
with x as (
    select exchange, asset, day_utc, lag(day_utc) over (partition by exchange, asset order by day_utc) as prev
    from {{ ref('stg_candles') }}
)
select * from x where prev is not null and day_utc - prev <> 1
