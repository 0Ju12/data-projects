-- 날 종류 분석표의 날짜 수 합이 일 요약 표의 날짜 수와 같아야 함 (분류에서 빠지는 날이 없게)
select (select sum(days) from {{ ref('ana_demand_by_daytype') }}) as classified,
       (select count(*) from {{ ref('fct_demand_daily') }}) as total
where (select sum(days) from {{ ref('ana_demand_by_daytype') }}) <> (select count(*) from {{ ref('fct_demand_daily') }})
