-- 사실 표: 한 행 = 재해 사건 하나 (최신 상태). 지속 일수와 경보 등급 순위를 붙임
select
    e.event_key,
    e.event_type,
    t.type_name,
    e.name,
    e.country,
    e.iso3,
    e.alert_level,
    case e.alert_level when 'Red' then 3 when 'Orange' then 2 else 1 end as alert_rank,
    e.severity,
    e.severity_unit,
    e.from_at,
    e.to_at,
    greatest(date_diff('day', e.from_at, e.to_at), 0) + 1              as duration_days,
    e.is_current,
    e.modified_at,
    e.lon,
    e.lat
from {{ ref('stg_disasters') }} e
join {{ ref('dim_disaster_type') }} t using (event_type)
