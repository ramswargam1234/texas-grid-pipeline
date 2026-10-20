-- Fuel-type generation should add up to ERCOT's total net generation. Flag hours more than 3% apart.
-- Warn rather than fail: EIA publishes the two datasets separately and they occasionally disagree.
{{ config(severity = 'warn') }}
with fuel as (
    select period_utc, sum(generation_mwh) as fuel_total_mwh, count(*) as fuels
    from {{ ref('stg_eia__ercot_fuel_hourly') }}
    group by 1
)

select f.period_utc, f.fuel_total_mwh, g.net_generation_mwh, f.fuels
from fuel f
join {{ ref('int_grid__hourly_pivoted') }} g using (period_utc)
where g.net_generation_mwh > 0
  and abs(f.fuel_total_mwh - g.net_generation_mwh) / g.net_generation_mwh > 0.03
