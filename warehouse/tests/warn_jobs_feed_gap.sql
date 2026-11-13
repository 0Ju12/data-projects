-- 수집 구간에 빈틈이 생긴 날: 그날 받은 공고 가운데 전에 본 것이 하나도 없으면(overlap = no) 그 사이 공고를 놓쳤을 수 있습니다.
-- 수집 실패(error:…)도 함께 보여 줍니다. 실패가 아니라 경고 — 지나간 공고는 다시 받을 수 없으므로 사실을 남기는 것이 목적입니다.
{{ config(severity = 'warn') }}
select run_date, source, overlap, fetched, pages
from {{ ref('stg_jobs_fetch_log') }}
where overlap = 'no' or overlap like 'error%'
