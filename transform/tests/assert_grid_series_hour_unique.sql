select period_utc, series_key, count(*) as n
from {{ ref('fct_grid_series_hourly') }}
group by 1, 2
having count(*) > 1
