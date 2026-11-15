-- (레지스트리, 패키지, 날) 은 한 줄
select registry, package, day, count(*) from {{ ref('stg_pkg_downloads') }} group by 1, 2, 3 having count(*) > 1
