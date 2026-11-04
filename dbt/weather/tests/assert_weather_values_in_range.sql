-- Fails for rows with implausible temperature (°C) or wind speed (km/h).
select *
from {{ ref('stg_weather_data') }}
where temperature not between -60 and 60
   or wind_speed not between 0 and 400
