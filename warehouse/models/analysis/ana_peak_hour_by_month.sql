-- 질문: 평일 하루 최대 수요는 몇 시에 나오나? (월별로 가장 흔한 시각)
select
    month(demand_date)                          as month,
    count(*)                                    as weekdays,
    mode(peak_hour_ending - 1)                  as usual_peak_hour_start,
    round(avg(peak_mw))                         as avg_peak_mw,
    max(peak_mw)                                as max_peak_mw,
    round(avg(temp_mean), 1)                    as avg_temp
from {{ ref('fct_demand_daily') }}
where day_type = 'weekday'
group by 1
