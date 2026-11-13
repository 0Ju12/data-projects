-- 이웃한 두 행의 간격은 항상 1시간이어야 합니다 ("24시"를 잘못 처리하면 여기서 걸림)
with x as (
    select hour_start_kst, lag(hour_start_kst) over (order by hour_start_kst) as prev
    from {{ ref('fct_demand_hourly') }}
)
select * from x where prev is not null and hour_start_kst - prev <> interval 1 hour
