-- 지역 차원: USGS 장소 설명의 마지막 쉼표 뒤 (예: "52 km E of Ulsan, South Korea" → South Korea)
select
    region,
    count(*)           as quakes,
    min(occurred_at_utc) as first_seen_utc,
    max(occurred_at_utc) as last_seen_utc
from {{ ref('stg_quakes') }}
group by 1
