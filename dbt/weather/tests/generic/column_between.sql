{% test column_between(model, column_name, min_value=none, max_value=none) %}
-- Returns rows whose non-null value falls outside [min_value, max_value].
select *
from {{ model }}
where {{ column_name }} is not null
  and (
    false
    {% if min_value is not none %} or {{ column_name }} < {{ min_value }} {% endif %}
    {% if max_value is not none %} or {{ column_name }} > {{ max_value }} {% endif %}
  )
{% endtest %}
