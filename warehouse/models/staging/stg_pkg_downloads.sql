-- 패키지 일일 내려받기 수 (PyPI 는 미러 제외 값, npm 은 레지스트리 집계)
select registry, package, cast(day as date) as day, cast(downloads as bigint) as downloads
from read_csv('{{ var("pkg_csv") }}', header = true, all_varchar = true)
