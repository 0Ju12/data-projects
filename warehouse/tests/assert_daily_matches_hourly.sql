-- 일 요약의 최대값은 시간 표에서 다시 계산한 값과 같아야 합니다 (집계 표와 원자료의 대조)
select d.demand_date, d.peak_mw, h.peak
from {{ ref('fct_demand_daily') }} d
join (select demand_date, max(demand_mw) as peak from {{ ref('fct_demand_hourly') }} group by 1) h using (demand_date)
where d.peak_mw <> h.peak or d.hours <> 24
