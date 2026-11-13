-- 전력거래소 시간별 수요 원본: 하루 한 줄, 열이 1시~24시 (그 시각에 "끝나는" 한 시간의 평균 MW)
select * from read_csv('{{ var("demand_csv") }}', header = true)
