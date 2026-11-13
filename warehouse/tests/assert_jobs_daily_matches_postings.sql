-- 일별 집계의 합이 공고 표의 행 수와 같아야 합니다
with a as (select sum(postings) as n from {{ ref('fct_jobs_daily') }}), b as (select count(*) as n from {{ ref('fct_job_postings') }})
select * from a, b where a.n <> b.n
