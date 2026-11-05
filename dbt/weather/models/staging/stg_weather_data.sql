with source as (

    select * from {{ source('weather', 'raw_weather_data') }}

),

converted as (

    select
        id,
        city,
        coalesce(nullif(payload #>> '{current,temperature}', '')::numeric, temperature) as temperature,
        coalesce(payload #>> '{current,weather_descriptions,0}', weather_description) as weather_description,
        coalesce(nullif(payload #>> '{current,wind_speed}', '')::numeric, wind_speed) as wind_speed,
        time as observed_at_local,
        time - (utc_offset || ' hours')::interval as observed_at_utc,
        utc_offset::numeric as utc_offset_hours,
        inserted_at as loaded_at_utc,

        payload #>> '{location,region}' as region,
        payload #>> '{location,country}' as country,
        {{ safe_numeric("payload #>> '{location,lat}'") }} as lat,
        {{ safe_numeric("payload #>> '{location,lon}'") }} as lon,
        payload #>> '{location,timezone_id}' as timezone_id,
        {{ safe_numeric("payload #>> '{current,feelslike}'") }} as feelslike,
        {{ safe_numeric("payload #>> '{current,humidity}'") }}::int as humidity,
        {{ safe_numeric("payload #>> '{current,pressure}'") }} as pressure,
        {{ safe_numeric("payload #>> '{current,precip}'") }} as precip,
        {{ safe_numeric("payload #>> '{current,cloudcover}'") }}::int as cloudcover,
        {{ safe_numeric("payload #>> '{current,uv_index}'") }} as uv_index,
        {{ safe_numeric("payload #>> '{current,visibility}'") }} as visibility,
        {{ safe_numeric("payload #>> '{current,wind_degree}'") }}::int as wind_degree,
        payload #>> '{current,wind_dir}' as wind_dir,
        {{ safe_numeric("payload #>> '{current,weather_code}'") }}::int as weather_code,
        case lower(payload #>> '{current,is_day}')
            when 'yes' then true
            when 'no' then false
        end as is_day,
        {{ safe_time("payload #>> '{current,astro,sunrise}'") }} as sunrise,
        {{ safe_time("payload #>> '{current,astro,sunset}'") }} as sunset,
        {{ safe_time("payload #>> '{current,astro,moonrise}'") }} as moonrise,
        {{ safe_time("payload #>> '{current,astro,moonset}'") }} as moonset,
        payload #>> '{current,astro,moon_phase}' as moon_phase,
        {{ safe_numeric("payload #>> '{current,astro,moon_illumination}'") }}::int as moon_illumination,
        {{ safe_numeric("payload #>> '{current,air_quality,co}'") }} as aq_co,
        {{ safe_numeric("payload #>> '{current,air_quality,no2}'") }} as aq_no2,
        {{ safe_numeric("payload #>> '{current,air_quality,o3}'") }} as aq_o3,
        {{ safe_numeric("payload #>> '{current,air_quality,so2}'") }} as aq_so2,
        {{ safe_numeric("payload #>> '{current,air_quality,pm2_5}'") }} as aq_pm2_5,
        {{ safe_numeric("payload #>> '{current,air_quality,pm10}'") }} as aq_pm10,
        {{ safe_numeric("payload #>> '{current,air_quality,us-epa-index}'") }}::int as us_epa_index,
        {{ safe_numeric("payload #>> '{current,air_quality,gb-defra-index}'") }}::int as gb_defra_index,
        source
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
    loaded_at_utc,
    region,
    country,
    lat,
    lon,
    timezone_id,
    feelslike,
    humidity,
    pressure,
    precip,
    cloudcover,
    uv_index,
    visibility,
    wind_degree,
    wind_dir,
    weather_code,
    is_day,
    sunrise,
    sunset,
    moonrise,
    moonset,
    moon_phase,
    moon_illumination,
    aq_co,
    aq_no2,
    aq_o3,
    aq_so2,
    aq_pm2_5,
    aq_pm10,
    us_epa_index,
    gb_defra_index,
    source
from deduplicated
where rn = 1
