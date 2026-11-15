-- 경보 등급이 바뀐 이력 (snapshot 에서): 사건마다 등급이 언제 무엇에서 무엇으로 바뀌었나
with v as (
    select event_key, alert_level, dbt_valid_from,
           lag(alert_level) over (partition by event_key order by dbt_valid_from) as prev_level
    from {{ ref('snap_disasters') }}
)
select event_key, prev_level, alert_level as new_level, dbt_valid_from as changed_at
from v
where prev_level is not null and prev_level <> alert_level
