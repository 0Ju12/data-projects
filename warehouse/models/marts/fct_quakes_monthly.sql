-- 월 × 지역 지진 수와 최대 규모 (종류가 earthquake 인 것만)
-- 증분 모델: 지난 실행 뒤에 새로 들어오거나 고쳐진 지진이 속한 (월, 지역) 묶음만 다시 계산해 바꿔 넣습니다.
-- 기준은 원본의 수정 시각(updated_at) — 발생 시각을 기준으로 하면 예전 지진이 나중에 고쳐진 경우를 놓칩니다.
{{ config(materialized = 'incremental', unique_key = ['month_kst', 'region'], incremental_strategy = 'delete+insert') }}

with src as (
    select *, date_trunc('month', occurred_at_kst)::date as month_kst
    from {{ ref('stg_quakes') }}
    where event_type = 'earthquake'
)
{% if is_incremental() %}
, touched as (
    select distinct month_kst, region
    from src
    where updated_at > (select coalesce(max(last_updated_at), timestamp '1900-01-01') from {{ this }})
)
{% endif %}
select
    s.month_kst,
    s.region,
    count(*)                    as quakes,
    max(s.mag)                  as max_mag,
    round(avg(s.depth_km), 1)   as mean_depth_km,
    max(s.updated_at)           as last_updated_at
from src s
{% if is_incremental() %}
join touched t on t.month_kst = s.month_kst and t.region = s.region
{% endif %}
group by 1, 2
