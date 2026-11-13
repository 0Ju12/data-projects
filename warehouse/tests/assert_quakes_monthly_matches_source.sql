-- 증분으로 쌓은 월별 집계의 합계가 원본에서 다시 센 값과 같아야 합니다.
-- 증분 모델은 "안 바뀐 묶음은 그대로 둔다"는 가정에 기대므로, 가정이 깨지면(예: 지진이 원본에서 빠짐) 여기서 드러납니다.
with a as (select sum(quakes) as n, max(max_mag) as m from {{ ref('fct_quakes_monthly') }}),
     b as (select count(*) as n, max(mag) as m from {{ ref('stg_quakes') }} where event_type = 'earthquake')
select a.n as mart_rows, b.n as source_rows, a.m as mart_max, b.m as source_max
from a, b
where a.n <> b.n or a.m <> b.m
