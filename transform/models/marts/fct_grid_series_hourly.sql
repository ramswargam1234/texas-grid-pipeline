-- Star-schema fact: one row per hour per EIA series (demand, forecast, generation).
-- The narrow "long" grain makes adding a new series a data change, not a schema change.
select
    s.period_utc,
    cast(strftime(s.period_utc at time zone 'America/Chicago', '%Y%m%d') as integer) as date_key,
    extract('hour' from s.period_utc at time zone 'America/Chicago')                 as hour_local,
    'ERCO'                                                                           as zone_key,
    s.series_type                                                                    as series_key,
    s.value_mwh
from {{ ref('stg_eia__ercot_hourly') }} s
