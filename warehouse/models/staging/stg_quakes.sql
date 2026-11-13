-- 지진 목록 원본(USGS) → 이름·형 정리. 한 행 = 지진 한 건의 최신 판
select
    id                                             as quake_id,
    cast(time_utc as timestamp)                    as occurred_at_utc,
    cast(time_kst as timestamp)                    as occurred_at_kst,
    to_timestamp(updated / 1000.0)::timestamp      as updated_at,
    cast(lat as double)                            as lat,
    cast(lon as double)                            as lon,
    cast(depth_km as double)                       as depth_km,
    cast(mag as double)                            as mag,
    mag_type,
    place,
    trim(split_part(place, ',', -1))               as region,
    status,
    type                                           as event_type
from read_csv('{{ var("quakes_csv") }}', header = true, all_varchar = false)
