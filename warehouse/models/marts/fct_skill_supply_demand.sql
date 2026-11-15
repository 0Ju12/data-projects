-- 기술별로 두 자료를 나란히: 공고에서의 언급(최근 4주)과, 짝지은 패키지의 내려받기(최근 4주 · 그 전 4주 대비)
-- 두 값은 단위도 모집단도 달라 서로 나눌 수 없습니다. 같은 기술을 두 각도에서 보는 표입니다.
with last_week as (select max(week_start) as w from {{ ref('fct_pkg_weekly') }}),
dl as (
    select skill,
           sum(downloads) filter (where week_start >  (select w from last_week) - 28)                                              as downloads_4w,
           sum(downloads) filter (where week_start <= (select w from last_week) - 28 and week_start > (select w from last_week) - 56) as downloads_prev_4w,
           string_agg(distinct package, ', ' order by package)                                                                       as packages
    from {{ ref('fct_pkg_weekly') }}
    group by 1
),
jobs as (
    select skill, count(distinct job_key) as postings_4w
    from {{ ref('int_job_skills') }}
    where posted_date >= (select max(posted_date) from {{ ref('int_job_skills') }}) - 27
    group by 1
)
select
    d.skill,
    k.category,
    coalesce(j.postings_4w, 0)                                             as postings_4w,
    d.downloads_4w,
    d.downloads_prev_4w,
    round((d.downloads_4w * 1.0 / nullif(d.downloads_prev_4w, 0) - 1) * 100, 2) as downloads_change_pct,
    d.packages
from dl d
join {{ ref('dim_skill') }} k using (skill)
left join jobs j using (skill)
