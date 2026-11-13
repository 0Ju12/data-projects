-- 지진 목록의 가장 최근 수정 시각이 너무 오래됐으면 경고 (수집이 멈췄는지 확인). 실패가 아니라 경고입니다.
{{ config(severity = 'warn') }}
select max(updated_at) as last_update
from {{ ref('stg_quakes') }}
having max(updated_at) < current_timestamp::timestamp - interval '{{ var("quake_fresh_days") }} days'
