-- 질문 7. 저탄소 발전 비중과 탄소 집약도 — 나라별로 어디쯤 있고 어떻게 움직였나? (연도별, 연도 재생용)
select
    country, year,
    low_carbon_share_elec   as low_carbon,
    carbon_intensity_elec   as intensity,
    per_capita_electricity  as per_capita_kwh,
    electricity_generation  as generation_twh
from owid
where year >= 2000 and low_carbon_share_elec is not null and carbon_intensity_elec is not null
order by 1, 2
