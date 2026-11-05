{# Defensive parsers for Weatherstack's string-typed values. Return NULL instead of failing. #}

{% macro safe_numeric(expr) -%}
    (case when ({{ expr }}) ~ '^\s*-?[0-9]+(\.[0-9]+)?\s*$' then trim({{ expr }})::numeric end)
{%- endmacro %}

{# '05:41 AM' -> time; anything else ('No moonrise', '') -> NULL #}
{% macro safe_time(expr) -%}
    (case when ({{ expr }}) ~* '^\s*(0?[1-9]|1[0-2]):[0-5][0-9]\s*(AM|PM)\s*$'
        then to_timestamp(upper(trim({{ expr }})), 'HH12:MI AM')::time end)
{%- endmacro %}
