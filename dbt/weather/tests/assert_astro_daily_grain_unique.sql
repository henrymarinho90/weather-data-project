-- Fails for every (city, date) that appears more than once.
select city, date, count(*) as n
from {{ ref('astro_daily') }}
group by city, date
having count(*) > 1
