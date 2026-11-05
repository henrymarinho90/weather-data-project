select
    city,
    observed_at_local::date as date,
    count(*) as n_observations,
    round(avg(aq_pm2_5)::numeric, 2) as avg_pm2_5,
    round(avg(aq_pm10)::numeric, 2) as avg_pm10,
    round(avg(aq_o3)::numeric, 2) as avg_o3,
    round(avg(aq_no2)::numeric, 2) as avg_no2,
    round(avg(aq_so2)::numeric, 2) as avg_so2,
    round(avg(aq_co)::numeric, 2) as avg_co,
    max(us_epa_index) as max_us_epa_index
from {{ ref('stg_weather_data') }}
where aq_pm2_5 is not null
   or aq_pm10 is not null
   or aq_o3 is not null
   or aq_no2 is not null
   or aq_so2 is not null
   or aq_co is not null
   or us_epa_index is not null
group by
    city,
    observed_at_local::date
