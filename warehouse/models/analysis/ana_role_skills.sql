-- 질문: 데이터 직무별로 공고에 어떤 기술이 얼마나 자주 나오나?
-- share_pct = 그 직무 공고 가운데 기술 이름이 나온 공고 비율 (기술 사전에 있는 이름만)
with r as (
    select job_key, replace(skill, ' (role)', '') as role
    from {{ ref('int_job_skills') }}
    where skill in ('Data Engineer (role)', 'Data Analyst (role)', 'Data Scientist (role)')
),
n as (select role, count(*) as postings from r group by 1),
s as (
    select r.role, k.skill, count(distinct r.job_key) as mentions
    from r
    join {{ ref('int_job_skills') }} k using (job_key)
    where k.skill not like '%(role)'
    group by 1, 2
)
select
    s.role,
    s.skill,
    d.category,
    s.mentions,
    n.postings,
    round(100.0 * s.mentions / n.postings, 1)                       as share_pct
from s
join n using (role)
join {{ ref('dim_skill') }} d using (skill)
