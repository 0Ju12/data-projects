-- 봉 하나 안에서: 저가 ≤ 시가·종가 ≤ 고가
select * from {{ ref('stg_candles') }}
where low > high or open < low or open > high or close < low or close > high
