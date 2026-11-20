-- 질문 1. 한국 발전 구성은 25년 동안 어떻게 바뀌었나? (OWID 연간, 발전량 비중 %)
-- 수력·바이오·석유·기타 재생은 한국에서 각각 1% 안팎이라 '기타'로 합침
select
    year,
    coal_share_elec                                         as coal,
    nuclear_share_elec                                      as nuclear,
    gas_share_elec                                          as gas,
    coalesce(oil_share_elec, 0) + coalesce(hydro_share_elec, 0)
      + coalesce(biofuel_share_elec, 0) + coalesce(other_renewables_share_elec_exc_biofuel, 0) as other,
    wind_share_elec                                         as wind,
    solar_share_elec                                        as solar,
    electricity_generation                                  as generation_twh,
    carbon_intensity_elec                                   as intensity
from owid
where country = 'South Korea' and year >= 2000 and coal_share_elec is not null
order by year
