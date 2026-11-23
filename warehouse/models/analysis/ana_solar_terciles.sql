-- 질문: 같은 달 안에서 맑은 날과 흐린 날의 한낮 수요는 얼마나 다른가?
-- 달마다 평일을 한낮 일사량 순으로 셋으로 나눔(1 = 가장 흐린 3분의 1, 3 = 가장 맑은 3분의 1).
-- 같은 달끼리만 비교하므로 계절에 따른 일사량·수요 차이는 섞이지 않습니다.
with ranked as (
    select *, ntile(3) over (partition by month order by midday_rad) as sun_tercile
    from {{ ref('ana_solar_daily') }}
)
select
    month,
    sun_tercile,
    case sun_tercile when 1 then '흐림' when 2 then '중간' else '맑음' end   as sun_label,
    count(*)                                            as days,
    round(avg(midday_rad))                              as midday_rad,
    round(avg(midday_cloud))                            as midday_cloud,
    round(avg(midday_temp), 1)                          as midday_temp,
    round(avg(midday_mw))                               as midday_mw,
    round(avg(midday_vs_night), 3)                      as midday_vs_night
from ranked
group by 1, 2, 3
