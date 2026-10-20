-- Daily totals per EIA series (Central-time days). The snapshot watches these for revisions:
-- if EIA republishes a day with different numbers, the snapshot keeps both versions.
select
    cast(period_utc at time zone 'America/Chicago' as date)   as date_local,
    series_type                                                as series_key,
    round(sum(value_mwh), 0)                                   as total_mwh,
    count(value_mwh)                                           as hours_reported,
    date_local || '|' || series_type                           as snapshot_key
from {{ ref('stg_eia__ercot_hourly') }}
group by 1, 2
