with source as (

    select * from {{ source('weather', 'raw_weather_data') }}

),

converted as (

    select
        id,
        city,
        temperature,
        weather_description,
        wind_speed,
        time as observed_at_local,
        time - (utc_offset || ' hours')::interval as observed_at_utc,
        utc_offset::numeric as utc_offset_hours,
        inserted_at as loaded_at_utc
    from source

),

deduplicated as (

    select
        *,
        row_number() over (
            partition by city, observed_at_utc
            order by loaded_at_utc, id
        ) as rn
    from converted

)

select
    id,
    city,
    temperature,
    weather_description,
    wind_speed,
    observed_at_local,
    observed_at_utc,
    utc_offset_hours,
    loaded_at_utc
from deduplicated
where rn = 1
