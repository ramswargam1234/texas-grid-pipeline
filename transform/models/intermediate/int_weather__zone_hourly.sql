-- Average temperature per ERCOT weather zone per hour, from the zone's reference city (or cities).
select
    w.period_utc,
    z.zone_code,
    avg(w.temp_f)       as zone_temp_f,
    avg(w.humidity_pct) as zone_humidity_pct,
    count(*)            as cities_reporting
from {{ ref('stg_weather__hourly') }} w
join {{ ref('ercot_zone_cities') }} z on z.weather_city = w.city
group by 1, 2
