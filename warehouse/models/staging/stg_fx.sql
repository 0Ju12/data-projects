-- 기준환율 (1 USD = rate × quote). 유럽중앙은행 고시일(영업일)에만 행이 있습니다
select cast(day as date) as fx_day, base, quote, cast(rate as double) as rate
from read_csv('{{ var("fx_csv") }}', header = true, all_varchar = true)
