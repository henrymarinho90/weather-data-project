-- One row per city and local date: the latest observation of the day that has payload data.
with ranked as (

    select
        *,
        row_number() over (
            partition by city, observed_at_local::date
            order by observed_at_utc desc, id desc
        ) as rn
    from {{ ref('stg_weather_data') }}
    where sunrise is not null
       or sunset is not null
       or moonrise is not null
       or moonset is not null
       or moon_phase is not null
       or moon_illumination is not null

)

select
    city,
    observed_at_local::date as date,
    sunrise,
    sunset,
    (extract(epoch from (sunset - sunrise)) / 60)::int as day_length_minutes,
    moonrise,
    moonset,
    moon_phase,
    moon_illumination
from ranked
where rn = 1
