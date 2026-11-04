-- Fails for every (city, observed_at_utc) that appears more than once.
select city, observed_at_utc, count(*) as n
from {{ ref('weather_report') }}
group by city, observed_at_utc
having count(*) > 1
