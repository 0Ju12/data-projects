-- 질문 6. 전력 1kWh 를 만들 때 나오는 탄소는 줄고 있나? (월별 배출 집약도, gCO2e/kWh, 12개월 이동 평균 포함)
select
    area,
    month,
    intensity_g_per_kwh                                                         as intensity,
    avg(intensity_g_per_kwh) over (partition by area order by month rows between 11 preceding and current row) as intensity_12m,
    count(*) over (partition by area order by month rows between 11 preceding and current row)               as months_in_window
from ember
where source = 'Total generation' and area in ('South Korea', 'Japan', 'Germany')
order by 1, 2
