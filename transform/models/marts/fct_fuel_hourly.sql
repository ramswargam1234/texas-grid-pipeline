-- One row per hour and fuel type, with each fuel's share of that hour's generation.
-- Battery charging (negative MWh) is kept as-is but left out of the hourly total, so shares add up to 100%.
with fuel as (
    select * from {{ ref('stg_eia__ercot_fuel_hourly') }}
),

hour_totals as (
    select period_utc, sum(greatest(generation_mwh, 0)) as hour_generation_mwh
    from fuel
    group by 1
)

select
    f.period_utc,
    cast(strftime(f.period_utc at time zone 'America/Chicago', '%Y%m%d') as integer) as date_key,
    (f.period_utc at time zone 'America/Chicago')               as period_local,
    cast(f.period_utc at time zone 'America/Chicago' as date)   as date_local,
    extract('hour' from f.period_utc at time zone 'America/Chicago') as hour_local,
    f.fuel_code                                                 as fuel_key,
    coalesce(d.fuel_label, f.fuel_name, f.fuel_code)            as fuel_label,
    coalesce(d.fuel_group, 'Other')                             as fuel_group,
    coalesce(d.is_renewable, false)                             as is_renewable,
    coalesce(d.is_carbon_free, false)                           as is_carbon_free,
    f.generation_mwh,
    greatest(f.generation_mwh, 0) / nullif(t.hour_generation_mwh, 0) as share_of_hour
from fuel f
join hour_totals t using (period_utc)
left join {{ ref('dim_fuel') }} d on d.fuel_key = f.fuel_code
