select
    city,
    temperature,
    weather_description,
    wind_speed,
    observed_at_local,
    observed_at_utc
from {{ ref('stg_weather_data') }}
