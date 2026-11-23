-- 질문: 맑은 날과 흐린 날의 하루 수요 곡선은 어느 시간대에서 갈라지는가?
-- 계절 × (같은 달 안의 맑음/흐림 구분) × 시각별 평균 수요. 중간 3분의 1은 빼고 양 끝만 비교.
with tercile as (
    select demand_date, ntile(3) over (partition by month order by midday_rad) as sun_tercile
    from {{ ref('ana_solar_daily') }}
)
select
    d.season,
    case t.sun_tercile when 1 then '흐림' else '맑음' end      as sun_label,
    f.hour_ending - 1                                           as hour_start,
    count(*)                                                    as days,
    round(avg(f.demand_mw))                                     as demand_mw
from {{ ref('fct_demand_hourly') }} f
join {{ ref('dim_date') }} d on d.date_day = f.demand_date
join tercile t on t.demand_date = f.demand_date
where t.sun_tercile in (1, 3)
group by 1, 2, 3
