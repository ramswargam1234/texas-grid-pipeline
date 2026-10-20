-- One day-ahead weather forecast per (hour, city).
{{ config(tags = ['forecast']) }}
select period_utc, city, count(*) as n
from {{ ref('stg_weather_forecast__hourly') }}
group by 1, 2
having count(*) > 1
