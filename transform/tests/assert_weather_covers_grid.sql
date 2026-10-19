-- Every grid hour should have weather for all 4 cities (the archive lags ~6 days, so recent hours are excused).
{{ config(severity = 'warn') }}
select period_utc, cities_reporting
from {{ ref('fct_grid_hourly') }} f
left join {{ ref('int_weather__texas_hourly') }} w using (period_utc)
where f.period_utc < now() - interval 8 day
  and coalesce(w.cities_reporting, 0) < 4
