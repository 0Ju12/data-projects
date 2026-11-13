-- 수집 기록: 하루 × 출처 한 줄. overlap = 그날 받은 구간이 전에 받은 구간과 이어졌는가 (first_run · yes · no · error:…)
select
    cast(run_date as date)        as run_date,
    source,
    cast(fetched as integer)      as fetched,
    cast("new" as integer)        as new_jobs,
    cast(changed as integer)      as changed_jobs,
    cast(pages as integer)        as pages,
    try_cast(nullif(oldest_posted_utc, '') as timestamp) as oldest_posted_utc,
    try_cast(nullif(newest_posted_utc, '') as timestamp) as newest_posted_utc,
    overlap
from read_csv('{{ var("jobs_fetch_csv") }}', header = true, all_varchar = true)
