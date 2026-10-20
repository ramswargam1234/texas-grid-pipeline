-- One row per (hour, fuel type) in the fuel fact table.
select period_utc, fuel_key, count(*) as n
from {{ ref('fct_fuel_hourly') }}
group by 1, 2
having count(*) > 1
