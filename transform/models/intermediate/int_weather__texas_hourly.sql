-- Collapses the 4 big metros into one statewide weather signal per hour.
-- (Zone-level weather for the other cities is in int_weather__zone_hourly.)
-- Cooling/heating degree-hours (base 65°F) are the standard way utilities relate weather to load.
select
    period_utc,
    avg(temp_f)                                             as avg_temp_f,
    max(temp_f)                                             as max_temp_f,
    min(temp_f)                                             as min_temp_f,
    avg(feels_like_f)                                       as avg_feels_like_f,
    avg(humidity_pct)                                       as avg_humidity_pct,
    greatest(avg(temp_f) - 65, 0)                           as cooling_degree_hours,
    greatest(65 - avg(temp_f), 0)                           as heating_degree_hours,
    max(case when city = 'dallas'      then temp_f end)     as dallas_temp_f,
    max(case when city = 'houston'     then temp_f end)     as houston_temp_f,
    max(case when city = 'austin'      then temp_f end)     as austin_temp_f,
    max(case when city = 'san_antonio' then temp_f end)     as san_antonio_temp_f,
    count(*)                                                as cities_reporting
from {{ ref('stg_weather__hourly') }}
where city in ('dallas', 'houston', 'austin', 'san_antonio')
group by period_utc
