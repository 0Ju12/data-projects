-- 질문: 데이터 직무 공고(엔지니어·분석가·사이언티스트)는 몇 건이고, 공고 하나에 기술이 몇 개 나오나?
-- 직무는 공고 제목으로 분류 (seeds/skills.csv 의 role 항목)
with r as (
    select job_key, replace(skill, ' (role)', '') as role
    from {{ ref('int_job_skills') }}
    where skill in ('Data Engineer (role)', 'Data Analyst (role)', 'Data Scientist (role)')
)
select
    r.role,
    count(*)                                                        as postings,
    round(avg(p.skill_count - 1), 1)                                as avg_skills,       -- 직무 표시 1개는 빼고
    count(*) filter (where p.is_remote)                             as remote_postings,
    count(*) filter (where p.salary_quality = 'annual')             as salary_postings,
    min(p.first_seen)                                               as first_seen,
    max(p.last_seen)                                                as last_seen
from r
join {{ ref('fct_job_postings') }} p using (job_key)
group by 1
