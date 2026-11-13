-- 4개 도시 시간별 기온 (Open-Meteo). 열 이름을 영문으로
select
    cast("time" as timestamp) as observed_at_kst,
    cast("서울" as double)    as temp_seoul,
    cast("부산" as double)    as temp_busan,
    cast("대전" as double)    as temp_daejeon,
    cast("광주" as double)    as temp_gwangju,
    cast("mean" as double)    as temp_mean
from read_csv('{{ var("weather_csv") }}', header = true)
