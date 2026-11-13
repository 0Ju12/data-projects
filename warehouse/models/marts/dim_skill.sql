-- 기술 차원: 사전(seeds/skills.csv)에 있는 이름과 분류. 공고 수는 지금까지 모은 전체 기준
select
    k.skill,
    k.category,
    k.scope,
    count(distinct b.job_key) as postings
from {{ ref('skills') }} k
left join {{ ref('int_job_skills') }} b on b.skill = k.skill
group by 1, 2, 3
