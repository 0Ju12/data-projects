-- 질문: 쉬는 날에는 수요가 얼마나 줄어드나?  (공휴일은 일요일과 같은 묶음)
with d as (select * from {{ ref('fct_demand_daily') }}),
wd as (select avg(mean_mw) as mean_mw, avg(peak_mw) as peak_mw from d where day_type = 'weekday')
select
    d.day_type,
    count(*)                                                   as days,
    round(avg(d.mean_mw))                                      as mean_mw,
    round(avg(d.peak_mw))                                      as peak_mw,
    round(100.0 * (avg(d.mean_mw) / (select mean_mw from wd) - 1), 1) as mean_vs_weekday_pct,
    round(100.0 * (avg(d.peak_mw) / (select peak_mw from wd) - 1), 1) as peak_vs_weekday_pct
from d
group by 1
