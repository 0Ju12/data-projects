-- 자연재해 경보 (GDACS). 한 행 = 사건 하나의 최신 상태
select
    event_key,
    event_type,
    name,
    nullif(country, '')                              as country,
    nullif(iso3, '')                                 as iso3,
    alert_level,
    try_cast(alert_score as double)                  as alert_score,
    try_cast(severity as double)                     as severity,
    nullif(severity_unit, '')                        as severity_unit,
    cast(from_date as timestamp)                     as from_at,
    cast(to_date as timestamp)                       as to_at,
    cast(modified_at as timestamp)                   as modified_at,
    try_cast(lon as double)                          as lon,
    try_cast(lat as double)                          as lat,
    is_current = 'true'                              as is_current
from read_csv('{{ var("disasters_csv") }}', header = true, all_varchar = true)
