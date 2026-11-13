-- (거래소, 자산, 날) 은 한 줄
select exchange, asset, day_utc, count(*) from {{ ref('stg_candles') }} group by 1, 2, 3 having count(*) > 1
