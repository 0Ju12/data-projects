{# 범위 검사: 값이 [min_value, max_value] 밖이면 실패 행으로 돌려줍니다 #}
{% test accepted_range(model, column_name, min_value=none, max_value=none) %}
select {{ column_name }} as value
from {{ model }}
where {{ column_name }} is not null and (
    {% if min_value is not none %}{{ column_name }} < {{ min_value }}{% else %}false{% endif %}
    or
    {% if max_value is not none %}{{ column_name }} > {{ max_value }}{% else %}false{% endif %}
)
{% endtest %}
