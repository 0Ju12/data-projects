-- 종류 차원에 없는 코드의 사건은 조인에서 조용히 빠집니다 — 원본과 사실 표의 행 수가 같아야 합니다
with a as (select count(*) n from {{ ref('stg_disasters') }}), b as (select count(*) n from {{ ref('fct_disaster_events') }})
select * from a, b where a.n <> b.n
