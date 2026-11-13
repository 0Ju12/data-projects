-- 사실 표: 한 행 = 공고 한 건
select
    j.job_key,
    j.source,
    j.posted_date,
    j.posted_at_utc,
    j.is_remote,
    j.title,
    j.company,
    j.location,
    j.salary_min_usd,
    j.salary_max_usd,
    -- 급여 칸은 단위가 섞여 있습니다(시급 21, 월급 4000, 천 단위 생략 110~130, 센트로 보이는 114000000 …).
    -- 어느 단위인지 추측해 고치지 않고, 연봉으로 볼 수 있는 범위(1만~100만 달러)만 쓰고 나머지는 표시만 해 둡니다.
    case when j.salary_min_usd is null or j.salary_max_usd is null or j.salary_min_usd <= 0 or j.salary_max_usd <= 0 then 'none'
         when j.salary_min_usd > j.salary_max_usd                                   then 'suspect_order'
         when j.salary_min_usd < 10000                                              then 'suspect_low'
         when j.salary_max_usd > 1000000                                            then 'suspect_high'
         else 'annual' end                                                          as salary_quality,
    case when j.salary_min_usd between 10000 and 1000000 and j.salary_max_usd between 10000 and 1000000
              and j.salary_min_usd <= j.salary_max_usd
         then (j.salary_min_usd + j.salary_max_usd) / 2.0 end                       as salary_mid_usd,
    coalesce(n.skill_count, 0)          as skill_count,
    coalesce(n.skill_count, 0) > 0      as is_tech,
    j.first_seen,
    j.last_seen,
    j.changed_on,
    j.url
from {{ ref('stg_jobs') }} j
left join (select job_key, count(*) as skill_count from {{ ref('int_job_skills') }} group by 1) n using (job_key)
