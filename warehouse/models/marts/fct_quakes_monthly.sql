-- 월 × 지역 지진 수와 최대 규모 (종류가 earthquake 인 것만)
select
    date_trunc('month', occurred_at_kst)::date as month_kst,
    region,
    count(*)            as quakes,
    max(mag)            as max_mag,
    round(avg(depth_km), 1) as mean_depth_km
from {{ ref('stg_quakes') }}
where event_type = 'earthquake'
group by 1, 2
