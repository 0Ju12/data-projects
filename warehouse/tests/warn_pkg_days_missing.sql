-- 패키지마다 날짜가 이어져야 합니다. 통계 서비스가 하루를 건너뛰는 일이 있어 실패가 아닌 경고로 둡니다
{{ config(severity = 'warn') }}
with x as (
    select registry, package, day, lag(day) over (partition by registry, package order by day) as prev
    from {{ ref('stg_pkg_downloads') }}
)
select * from x where prev is not null and day - prev <> 1
