-- Day-ahead weather forecasts per city and hour (latest ingested copy wins).
with ranked as (
    select
        cast(period_utc as timestamptz)          as period_utc,
        city,
        cast(forecast_temp_f as double)          as forecast_temp_f,
        cast(forecast_humidity_pct as double)    as forecast_humidity_pct,
        cast(lead_hours as integer)              as lead_hours,
        weather_model,
        row_number() over (partition by period_utc, city order by ingested_at desc) as rn
    from {{ source('raw', 'weather_forecast_hourly') }}
)

select period_utc, city, forecast_temp_f, forecast_humidity_pct, lead_hours, weather_model
from ranked
where rn = 1
