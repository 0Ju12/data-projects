-- 질문: 1년 중 수요가 가장 높았던 날들은 어떤 날이었나? (상위 10일)
select
    row_number() over (order by peak_mw desc, demand_date) as peak_rank,
    demand_date,
    isodow(demand_date)                         as iso_dow,
    day_type,
    peak_mw,
    peak_hour_ending - 1                        as peak_hour_start,
    temp_mean
from {{ ref('fct_demand_daily') }}
qualify peak_rank <= 10
