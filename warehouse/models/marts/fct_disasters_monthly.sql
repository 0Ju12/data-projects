-- 시작한 달 × 종류: 사건 수와 주황·빨강 경보 수
select
    date_trunc('month', from_at)::date        as month,
    event_type,
    count(*)                                  as events,
    count(*) filter (where alert_rank >= 2)   as orange_or_red,
    count(*) filter (where alert_rank = 3)    as red
from {{ ref('fct_disaster_events') }}
group by 1, 2
