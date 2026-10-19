-- Fails if any (hour, series_type) pair appears more than once after de-duplication.
select period_utc, series_type, count(*) as n
from {{ ref('stg_eia__ercot_hourly') }}
group by 1, 2
having count(*) > 1
