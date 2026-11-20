-- 질문 5. 1년 안에서도 발전 구성이 바뀌나? (한국, 다 찬 최근 4개 연도의 달별 평균 비중)
with full_years as (
    select year(month) as y from ember
    where area = 'South Korea' and source = 'Total generation'
    group by 1 having count(*) = 12
    order by 1 desc limit 4
),
grouped as (
    select month(e.month) as mon, year(e.month) as y, g.grp, sum(e.share_pct) as share
    from ember e
    join grp g on g.source = e.source
    where e.area = 'South Korea' and year(e.month) in (select y from full_years)
    group by 1, 2, 3
)
select mon, grp, round(avg(share), 2) as share,
       (select min(y) from full_years) as from_year, (select max(y) from full_years) as to_year
from grouped
group by 1, 2
order by 1, 2
