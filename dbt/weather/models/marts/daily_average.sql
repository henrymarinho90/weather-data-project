select
    city,
    observed_at_local::date as date,
    count(*) as n_observations,
    round(avg(temperature)::numeric, 2) as avg_temperature,
    min(temperature) as min_temperature,
    max(temperature) as max_temperature,
    round(avg(wind_speed)::numeric, 2) as avg_wind_speed
from {{ ref('stg_weather_data') }}
group by
    city,
    observed_at_local::date
