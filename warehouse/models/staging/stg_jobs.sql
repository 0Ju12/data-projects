-- 채용 공고 (Remote OK · Arbeitnow). 한 행 = 공고 한 건의 최신 상태. 본문은 없고, 수집 때 뽑아 둔 기술 이름 목록만 있습니다
select
    source,
    job_id,
    source || ':' || job_id                       as job_key,
    title,
    company,
    nullif(location, '')                          as location,
    cast(remote as boolean)                       as is_remote,
    cast(posted_at_utc as timestamp)              as posted_at_utc,
    cast(posted_at_utc as timestamp)::date        as posted_date,
    try_cast(salary_min as integer)               as salary_min_usd,
    try_cast(salary_max as integer)               as salary_max_usd,
    url,
    coalesce(skills, '')                          as skills,
    skills_dict,
    cast(first_seen as date)                      as first_seen,
    cast(last_seen as date)                       as last_seen,
    try_cast(nullif(changed_on, '') as date)      as changed_on
from read_csv('{{ var("jobs_csv") }}', header = true, all_varchar = true)
