-- 패키지 차원: 어느 기술과 짝지었는지(seeds/packages.csv)와 자료가 있는 기간
select
    p.registry,
    p.package,
    p.skill,
    min(d.day)   as first_day,
    max(d.day)   as last_day,
    count(d.day) as days
from {{ ref('packages') }} p
left join {{ ref('stg_pkg_downloads') }} d using (registry, package)
group by 1, 2, 3
