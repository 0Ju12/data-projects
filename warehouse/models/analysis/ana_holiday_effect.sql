-- 질문: 긴 연휴(설·추석)에는 수요가 평소 평일·주말과 비교해 얼마나 낮나?
-- 비교 기준: 연휴 앞뒤 14일 안의 평일 / 주말 (연휴 기간은 뺌)
with periods as (
    select * from (values
        ('설 연휴',  date '2025-01-25', date '2025-01-30'),
        ('추석 연휴', date '2025-10-03', date '2025-10-09')
    ) t(period_name, start_date, end_date)
),
d as (select * from {{ ref('fct_demand_daily') }})
select
    p.period_name,
    p.start_date,
    p.end_date,
    count(*) filter (where d.demand_date between p.start_date and p.end_date)                     as holiday_days,
    round(avg(d.mean_mw) filter (where d.demand_date between p.start_date and p.end_date))        as holiday_mean_mw,
    round(avg(d.mean_mw) filter (where d.day_type = 'weekday' and not d.demand_date between p.start_date and p.end_date)) as near_weekday_mean_mw,
    round(avg(d.mean_mw) filter (where d.day_type <> 'weekday' and not d.demand_date between p.start_date and p.end_date)) as near_offday_mean_mw,
    round(100.0 * (avg(d.mean_mw) filter (where d.demand_date between p.start_date and p.end_date))
        / (avg(d.mean_mw) filter (where d.day_type = 'weekday' and not d.demand_date between p.start_date and p.end_date)) - 100, 1) as vs_weekday_pct,
    round(100.0 * (avg(d.mean_mw) filter (where d.demand_date between p.start_date and p.end_date))
        / (avg(d.mean_mw) filter (where d.day_type <> 'weekday' and not d.demand_date between p.start_date and p.end_date)) - 100, 1) as vs_offday_pct
from periods p
join d on d.demand_date between p.start_date - 14 and p.end_date + 14
group by 1, 2, 3
