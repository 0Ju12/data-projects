-- 환율을 달력의 모든 날로 넓힙니다. 주말·휴일은 직전 영업일 값을 쓰고(is_filled), 며칠 묵은 값인지(stale_days) 남깁니다.
-- 거래소는 365일 열려 있어서, 이렇게 하지 않으면 주말 시세를 원화↔달러로 환산할 수 없습니다.
with days as (
    select unnest(generate_series((select min(fx_day) from {{ ref('stg_fx') }}),
                                  (select max(day_utc) from {{ ref('stg_candles') }}), interval 1 day))::date as day
),
grid as (select d.day, q.quote from days d cross join (select distinct quote from {{ ref('stg_fx') }}) q),
joined as (
    select g.day, g.quote, f.rate, f.fx_day
    from grid g left join {{ ref('stg_fx') }} f on f.fx_day = g.day and f.quote = g.quote
)
select
    day,
    quote,
    last_value(rate ignore nulls)   over w                 as rate,
    last_value(fx_day ignore nulls) over w                 as rate_day,
    rate is null                                           as is_filled,
    day - last_value(fx_day ignore nulls) over w           as stale_days
from joined
window w as (partition by quote order by day rows between unbounded preceding and current row)
