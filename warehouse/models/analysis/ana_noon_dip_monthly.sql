-- 질문: 평일 한낮(12~13시) 수요가 새벽 최저보다도 낮아지는 날은 언제 많은가?
-- 점심시간 감소는 계절과 상관없이 나타나므로, 새벽(0~7시) 최저와 비교해 그보다 깊은 날만 셉니다.
with day as (
    select
        f.demand_date,
        max(f.demand_mw) filter (where f.hour_ending = 13)          as noon_mw,     -- 12:00~13:00
        min(f.demand_mw) filter (where f.hour_ending between 1 and 7) as night_min_mw  -- 0:00~7:00 최저
    from {{ ref('fct_demand_hourly') }} f
    join {{ ref('dim_date') }} d on d.date_day = f.demand_date
    where d.day_type = 'weekday'
    group by 1
)
select
    month(demand_date)                                          as month,
    count(*)                                                    as weekdays,
    count(*) filter (where noon_mw < night_min_mw)              as dip_days,
    round(avg(100.0 * (noon_mw / night_min_mw - 1)), 1)         as noon_vs_night_pct
from day
group by 1
