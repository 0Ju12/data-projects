-- 질문 3. 태양광은 나라마다 언제, 얼마나 빠르게 늘었나? (연도별 비중과 1%·5%·10% 를 처음 넘은 해)
select
    country,
    list({'year': year, 'solar': solar_share_elec, 'wind': wind_share_elec} order by year) as series,
    min(year) filter (where solar_share_elec >= 1)  as first_1pct,
    min(year) filter (where solar_share_elec >= 5)  as first_5pct,
    min(year) filter (where solar_share_elec >= 10) as first_10pct,
    arg_max(solar_share_elec, year)                 as solar_last
from owid
where year >= 2005 and solar_share_elec is not null
group by 1
