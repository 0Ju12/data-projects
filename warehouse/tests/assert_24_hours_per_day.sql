-- 하루는 정확히 24행이어야 합니다 (빠진 시간·겹친 시간 탐지)
select demand_date, count(*) as hours
from {{ ref('fct_demand_hourly') }}
group by 1
having count(*) <> 24
