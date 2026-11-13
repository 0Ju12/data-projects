-- 공고 × 기술 (다대다). 'Python|SQL|dbt' 같은 목록을 한 줄씩 풉니다
select
    j.job_key,
    j.source,
    j.posted_date,
    trim(s.skill) as skill
from {{ ref('stg_jobs') }} j,
     unnest(string_split(j.skills, '|')) as s(skill)
where j.skills <> '' and trim(s.skill) <> ''
