-- 질문: 기온에 따라 수요가 어떻게 달라지나?  일평균 기온 2°C 구간별 평균 (날 종류별로 따로)
select
    day_type,
    (floor(temp_mean / 2) * 2)::integer         as temp_bin_lo,     -- 이 값 이상 +2°C 미만
    count(*)                                    as days,
    round(avg(mean_mw))                         as mean_mw,
    round(avg(peak_mw))                         as peak_mw
from {{ ref('fct_demand_daily') }}
group by 1, 2
