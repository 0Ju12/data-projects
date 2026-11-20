-- 질문 2. 석탄 비중은 다른 나라와 비교해 얼마나 빨리 줄고 있나? (2015년 → 최근 연도, %p)
with last as (select max(year) as y from owid where coal_share_elec is not null)
select
    country,
    max(coal_share_elec) filter (where year = 2015)                         as coal_2015,
    max(coal_share_elec) filter (where year = (select y from last))         as coal_last,
    max(low_carbon_share_elec) filter (where year = 2015)                   as low_carbon_2015,
    max(low_carbon_share_elec) filter (where year = (select y from last))   as low_carbon_last,
    max(coal_share_elec)                                                    as coal_peak,
    arg_max(year, coal_share_elec)                                          as coal_peak_year,
    (select y from last)                                                    as last_year
from owid
where year >= 2000
group by 1
order by coal_last - coal_2015
