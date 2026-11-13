-- 사실 표: 한 행 = 한 시간의 전국 수요 + 그 시각 4개 도시 평균 기온
select
    h.hour_start_kst,
    h.demand_date,
    h.hour_ending,
    h.demand_mw,
    w.temp_mean
from {{ ref('int_demand_hourly') }} h
left join {{ ref('stg_weather') }} w on w.observed_at_kst = h.hour_start_kst
