select
    city,
    observed_at_local::date as date,
    count(*) as n_observations,
    round(avg(temperature)::numeric, 2) as avg_temperature,
    min(temperature) as min_temperature,
    max(temperature) as max_temperature,
    round(avg(wind_speed)::numeric, 2) as avg_wind_speed,
    round(avg(humidity)::numeric, 2) as avg_humidity,
    round(sum(precip)::numeric, 2) as total_precip,
    max(uv_index) as max_uv_index,
    round(avg(aq_pm2_5)::numeric, 2) as avg_pm2_5
from {{ ref('stg_weather_data') }}
group by
    city,
    observed_at_local::date
