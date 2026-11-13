-- 가로로 긴 표(날짜 × 24열)를 세로로 풉니다.
-- "24시" 는 그날 23:00~24:00 구간입니다. 다음 날 0시로 넘기지 않도록 "끝나는 시각"이 아니라 "시작 시각"을 키로 씁니다.
with long as (
    unpivot {{ ref('stg_demand_wide') }}
    on columns(* exclude ("날짜"))
    into name hour_label value demand_mw
)
select
    cast("날짜" as date)                                               as demand_date,
    cast(replace(hour_label, '시', '') as integer)                     as hour_ending,
    cast("날짜" as date) + to_hours(cast(replace(hour_label, '시', '') as integer) - 1) as hour_start_kst,
    cast(demand_mw as integer)                                         as demand_mw
from long
