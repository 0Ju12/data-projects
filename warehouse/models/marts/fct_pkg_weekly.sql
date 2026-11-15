-- 주 × 패키지 내려받기 수. 7일이 다 찬 주만 남깁니다 (덜 찬 주를 그대로 두면 마지막 주가 늘 급감한 것처럼 보임)
with w as (
    select registry, package, date_trunc('week', day)::date as week_start, sum(downloads) as downloads, count(*) as days
    from {{ ref('stg_pkg_downloads') }}
    group by 1, 2, 3
)
select
    w.registry,
    w.package,
    p.skill,
    w.week_start,
    w.downloads,
    lag(w.downloads) over (partition by w.registry, w.package order by w.week_start) as prev_downloads
from w
join {{ ref('packages') }} p using (registry, package)
where w.days = 7
