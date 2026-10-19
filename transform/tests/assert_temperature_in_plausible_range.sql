-- Texas temperatures outside -20°F .. 125°F indicate bad data.
select period_utc, city, temp_f
from {{ ref('stg_weather__hourly') }}
where temp_f < -20 or temp_f > 125
