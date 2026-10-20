-- Typical demand drop per holiday across years. Days whose temperature was more than 10°F away from
-- their baseline (e.g. Presidents' Day 2021, during Winter Storm Uri) are left out: there the weather,
-- not the holiday, drives the difference.
select
    holiday_name,
    bool_or(is_nerc_holiday)                                    as is_nerc_holiday,
    count(*) filter (where not is_distorted)                    as days,
    round(median(demand_change_pct) filter (where not is_distorted), 2) as median_change_pct,
    round(min(demand_change_pct) filter (where not is_distorted), 2)    as min_change_pct,
    round(max(demand_change_pct) filter (where not is_distorted), 2)    as max_change_pct,
    count(*) filter (where is_distorted)                        as weather_distorted_days_left_out
from (
    select *, coalesce(abs(temp_diff_f) > 10, false) as is_distorted
    from {{ ref('agg_holiday_effect') }}
)
group by holiday_name
