-- One row per (hour, city). Temperatures in Fahrenheit.
with source as (
    select * from {{ source('raw', 'weather_hourly') }}
),

ranked as (
    select
        cast(period_utc as timestamptz)  as period_utc,
        lower(city)                      as city,
        cast(temp_f as double)           as temp_f,
        cast(feels_like_f as double)     as feels_like_f,
        cast(humidity_pct as double)     as humidity_pct,
        ingested_at,
        row_number() over (
            partition by period_utc, city
            order by ingested_at desc
        ) as rn
    from source
    where temp_f is not null
)

select period_utc, city, temp_f, feels_like_f, humidity_pct, ingested_at
from ranked
where rn = 1
