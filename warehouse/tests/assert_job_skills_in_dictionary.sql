-- 공고에 붙은 기술 이름은 모두 사전에 있어야 합니다 (사전에서 이름을 바꾸거나 지우면 예전 공고의 이름이 떠돌게 됨)
select distinct b.skill
from {{ ref('int_job_skills') }} b
left join {{ ref('skills') }} k on k.skill = b.skill
where k.skill is null
