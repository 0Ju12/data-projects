-- 날짜 차원: 수요 자료에 있는 날짜 범위만큼
with d as (
    select unnest(generate_series(
        (select min(demand_date) from {{ ref('int_demand_hourly') }}),
        (select max(demand_date) from {{ ref('int_demand_hourly') }}),
        interval 1 day))::date as date_day
)
select
    date_day,
    year(date_day)                      as year,
    month(date_day)                     as month,
    isodow(date_day)                    as iso_dow,            -- 1=월 … 7=일
    isodow(date_day) >= 6               as is_weekend,
    case when month(date_day) in (12, 1, 2) then 'winter'
         when month(date_day) in (3, 4, 5)  then 'spring'
         when month(date_day) in (6, 7, 8)  then 'summer'
         else 'autumn' end              as season
from d
