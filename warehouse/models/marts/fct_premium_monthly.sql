-- 월 × 자산: 프리미엄의 평균·최소·최대와, 3% 를 넘은 날 수
select
    date_trunc('month', day_utc)::date     as month,
    asset,
    count(*)                               as days,
    round(avg(premium_pct), 3)             as avg_premium_pct,
    round(min(premium_pct), 3)             as min_premium_pct,
    round(max(premium_pct), 3)             as max_premium_pct,
    count(*) filter (where premium_pct > 3)  as days_over_3pct,
    count(*) filter (where premium_pct < 0)  as days_negative
from {{ ref('fct_krw_premium_daily') }}
group by 1, 2
