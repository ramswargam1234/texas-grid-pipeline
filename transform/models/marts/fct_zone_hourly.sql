-- One row per hour and ERCOT weather zone: zone demand joined to that zone's own weather.
with zones as (
    select distinct zone_code, zone_label from {{ ref('ercot_zone_cities') }}
)

select
    d.period_utc,
    cast(strftime(d.period_utc at time zone 'America/Chicago', '%Y%m%d') as integer) as date_key,
    (d.period_utc at time zone 'America/Chicago')        as period_local,
    cast(d.period_utc at time zone 'America/Chicago' as date) as date_local,
    extract('hour' from d.period_utc at time zone 'America/Chicago') as hour_local,
    d.zone_code,
    d.zone_code                                           as zone_key,
    z.zone_label,
    d.demand_mwh,
    w.zone_temp_f,
    w.zone_humidity_pct
from {{ ref('stg_eia__ercot_zone_hourly') }} d
left join zones z using (zone_code)
left join {{ ref('int_weather__zone_hourly') }} w using (period_utc, zone_code)
