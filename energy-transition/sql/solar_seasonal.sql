-- 질문 4. 한국 태양광 비중은 계절에 따라 어떻게 달라지나? (Ember 월별, 연 × 월)
select
    year(month)                     as year,
    month(month)                    as mon,
    share_pct                       as solar_share,
    generation_twh                  as solar_twh
from ember
where area = 'South Korea' and source = 'Solar'
order by 1, 2
