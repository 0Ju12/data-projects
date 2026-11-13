-- (월, 지역) 은 한 줄이어야 합니다 — 증분에서 바꿔 넣기가 아니라 덧붙이기가 되면 여기서 걸립니다
select month_kst, region, count(*) as n
from {{ ref('fct_quakes_monthly') }}
group by 1, 2
having count(*) > 1
