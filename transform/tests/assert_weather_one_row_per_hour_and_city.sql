select period_utc, city, count(*) as n
from {{ ref('stg_weather__hourly') }}
group by 1, 2
having count(*) > 1
