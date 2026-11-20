-- 질문: 하루 중 언제 수요가 몰리고, 계절마다 그 시각이 달라지나?
-- hour_start 는 그 시간의 시작 시각 (17 = 17:00~18:00)
select
    d.season,
    d.day_type,
    f.hour_ending - 1                           as hour_start,
    count(*)                                    as days,
    round(avg(f.demand_mw))                     as demand_mw
from {{ ref('fct_demand_hourly') }} f
join {{ ref('dim_date') }} d on d.date_day = f.demand_date
group by 1, 2, 3
