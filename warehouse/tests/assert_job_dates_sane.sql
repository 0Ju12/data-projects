-- 게시 시각이 미래이거나, 마지막으로 본 날이 처음 본 날보다 앞선 공고 (급여 순서 이상은 salary_quality 로 따로 표시)
select job_key, posted_at_utc, first_seen, last_seen, salary_min_usd, salary_max_usd
from {{ ref('fct_job_postings') }}
where posted_at_utc > current_timestamp::timestamp + interval 1 day
   or last_seen < first_seen
