-- One row per (hour, zone) in the zone fact table.
select period_utc, zone_code, count(*) as n
from {{ ref('fct_zone_hourly') }}
group by 1, 2
having count(*) > 1
