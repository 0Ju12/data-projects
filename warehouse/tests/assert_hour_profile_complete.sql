-- 시간대 분석표: (계절, 날 종류)마다 24개 시각이 모두 있어야 함 — 빠지면 그래프가 조용히 비틀어짐
select season, day_type, count(*) as hours
from {{ ref('ana_demand_hour_profile') }}
group by 1, 2
having count(*) <> 24
