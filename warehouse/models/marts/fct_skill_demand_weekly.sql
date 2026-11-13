-- 주 × 기술: 그 기술을 언급한 공고 수와, 그 주 기술 공고 가운데 비중
with weekly as (
    select date_trunc('week', posted_date)::date as week_start, skill, count(distinct job_key) as postings
    from {{ ref('int_job_skills') }}
    group by 1, 2
),
tech as (
    select date_trunc('week', posted_date)::date as week_start, count(*) as tech_postings
    from {{ ref('fct_job_postings') }}
    where is_tech
    group by 1
)
select
    w.week_start,
    w.skill,
    d.category,
    w.postings,
    t.tech_postings,
    round(w.postings * 1.0 / t.tech_postings, 4) as share_of_tech
from weekly w
join tech t using (week_start)
join {{ ref('dim_skill') }} d using (skill)
