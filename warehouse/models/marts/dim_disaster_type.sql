-- 재해 종류 차원 (GDACS 코드 → 이름, 규모 단위)
select * from (values
    ('TC', '태풍·열대저기압', 'km/h'),
    ('FL', '홍수', null),
    ('VO', '화산', null),
    ('DR', '가뭄', 'km2')
) as t(event_type, type_name, severity_unit)
