-- A day-ahead temperature forecast should be within 30°F of what actually happened at that city and hour.
-- Warn rather than fail: a bad forecast is real data, but this many degrees usually means a units or time bug.
{{ config(tags = ['forecast'], severity = 'warn') }}
select f.period_utc, f.city, f.forecast_temp_f, w.temp_f
from {{ ref('stg_weather_forecast__hourly') }} f
join {{ ref('stg_weather__hourly') }} w using (period_utc, city)
where abs(f.forecast_temp_f - w.temp_f) > 30
