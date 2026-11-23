-- 질문: 맑은 날 한낮 수요가 더 많이 내려가는가? (가설: 전력거래소가 계량하지 않는 태양광이 한낮 수요를 깎는다)
-- 평일 하루 = 한 행. 한낮 = 11:00~14:00, 새벽 기준 = 0:00~7:00 최저, 대조 구간 = 해가 진 20:00~23:00.
-- 대조 구간에는 해가 없으므로, 일사량이 이 구간 수요와도 관련 있다면 태양광이 아닌 다른 이유(날씨에 따른 활동 차이 등)를 의심합니다.
with hourly as (
    select
        f.demand_date,
        f.hour_ending,
        f.demand_mw,
        f.temp_mean,
        s.rad_mean,
        s.cloud_mean
    from {{ ref('fct_demand_hourly') }} f
    join {{ ref('dim_date') }} d on d.date_day = f.demand_date
    left join {{ ref('stg_solar') }} s
           on s.hour_end_kst = f.hour_start_kst + interval 1 hour
    where d.day_type = 'weekday'
)
select
    demand_date,
    month(demand_date)                                                      as month,
    round(avg(demand_mw)  filter (where hour_ending between 12 and 14))     as midday_mw,
    round(min(demand_mw)  filter (where hour_ending between 1 and 7))       as night_min_mw,
    round(avg(demand_mw)  filter (where hour_ending between 21 and 23))     as evening_mw,
    round(avg(temp_mean)  filter (where hour_ending between 12 and 14), 2)  as midday_temp,
    round(avg(temp_mean)  filter (where hour_ending between 21 and 23), 2)  as evening_temp,
    round(avg(rad_mean)   filter (where hour_ending between 12 and 14), 1)  as midday_rad,
    round(avg(cloud_mean) filter (where hour_ending between 12 and 14), 1)  as midday_cloud,
    round(avg(demand_mw)  filter (where hour_ending between 12 and 14)
        / min(demand_mw)  filter (where hour_ending between 1 and 7), 4)    as midday_vs_night
from hourly
group by 1
