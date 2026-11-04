-- Fails for every (city, observed_at_utc) that appears more than once.
select city, observed_at_utc, count(*) as n
from {{ ref('stg_weather_data') }}
group by city, observed_at_utc
having count(*) > 1
