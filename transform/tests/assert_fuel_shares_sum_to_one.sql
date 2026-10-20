-- Within each hour, fuel shares must add up to 100% (fails on a broken share calculation).
select period_utc, sum(share_of_hour) as total_share
from {{ ref('fct_fuel_hourly') }}
group by 1
having sum(share_of_hour) is not null and abs(sum(share_of_hour) - 1) > 0.0001
