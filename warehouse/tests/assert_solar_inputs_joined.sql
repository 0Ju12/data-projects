-- 일사량 결합 점검: 평일마다 한낮 일사량이 있어야 하고, 달마다 맑음·중간·흐림 세 묶음이 모두 있어야 함
-- (시각 맞춤이 한 시간 어긋나거나 파일이 일부만 들어오면 여기서 걸림)
select 'missing_rad' as problem, cast(demand_date as varchar) as k from {{ ref('ana_solar_daily') }} where midday_rad is null
union all
select 'tercile_gap', cast(month as varchar) from {{ ref('ana_solar_terciles') }} group by month having count(*) <> 3
