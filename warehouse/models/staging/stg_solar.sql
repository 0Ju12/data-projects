-- 4개 도시 시간별 일사량(W/m²)·운량(%) (Open-Meteo 과거 자료).
-- Open-Meteo 의 일사량은 '그 시각 직전 한 시간 평균'이라, time 13:00 = 12:00~13:00 값입니다.
-- 그래서 hour_end_kst 로 이름을 붙여, 수요의 hour_ending(같은 한 시간의 끝 시각)과 바로 맞출 수 있게 합니다.
select
    cast("time" as timestamp)       as hour_end_kst,
    cast(rad_seoul as double)       as rad_seoul,
    cast(rad_busan as double)       as rad_busan,
    cast(rad_daejeon as double)     as rad_daejeon,
    cast(rad_gwangju as double)     as rad_gwangju,
    cast(rad_mean as double)        as rad_mean,
    cast(cloud_mean as double)      as cloud_mean
from read_csv('{{ var("solar_csv") }}', header = true)
