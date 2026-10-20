-- The 8 weather zones should add up to ERCOT's total demand. Flag hours where they differ by more than 3%.
-- Warn rather than fail: EIA's two datasets are published separately and occasionally disagree.
{{ config(severity = 'warn') }}
with zones as (
    select period_utc, sum(demand_mwh) as zone_total_mwh, count(*) as zones
    from {{ ref('stg_eia__ercot_zone_hourly') }}
    group by 1
)

select z.period_utc, z.zone_total_mwh, g.demand_mwh as ercot_total_mwh, z.zones
from zones z
join {{ ref('int_grid__hourly_pivoted') }} g using (period_utc)
where g.demand_mwh > 0
  and abs(z.zone_total_mwh - g.demand_mwh) / g.demand_mwh > 0.03
