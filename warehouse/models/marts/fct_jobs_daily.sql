-- 일 × 출처: 게시된 공고 수, 그 가운데 기술 공고·원격 공고
select
    posted_date,
    source,
    count(*)                                         as postings,
    count(*) filter (where is_tech)                  as tech_postings,
    count(*) filter (where is_remote)                as remote_postings,
    count(*) filter (where salary_quality = 'annual')    as with_usable_salary,
    count(*) filter (where salary_quality like 'suspect%') as with_suspect_salary
from {{ ref('fct_job_postings') }}
group by 1, 2
