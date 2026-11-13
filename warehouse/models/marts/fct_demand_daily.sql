-- 하루 요약: 최대·최소·평균 수요, 최대가 난 시각, 부하율(평균/최대)
select
    f.demand_date,
    d.is_weekend,
    d.season,
    max(f.demand_mw)                              as peak_mw,
    min(f.demand_mw)                              as min_mw,
    round(avg(f.demand_mw), 1)                    as mean_mw,
    arg_max(f.hour_ending, f.demand_mw)           as peak_hour_ending,
    round(avg(f.demand_mw) / max(f.demand_mw), 4) as load_factor,
    round(avg(f.temp_mean), 2)                    as temp_mean,
    count(*)                                      as hours
from {{ ref('fct_demand_hourly') }} f
join {{ ref('dim_date') }} d on d.date_day = f.demand_date
group by 1, 2, 3
