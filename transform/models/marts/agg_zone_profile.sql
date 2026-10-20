-- One row per ERCOT weather zone: size, peak, and how strongly demand responds to local temperature.
with hourly as (
    select * from {{ ref('fct_zone_hourly') }}
    where demand_mwh is not null
),

totals as (
    select sum(demand_mwh) as all_zones_mwh from hourly
)

select
    h.zone_code,
    any_value(h.zone_label)                                                  as zone_label,
    count(*)                                                                 as hours,
    avg(h.demand_mwh)                                                        as avg_demand_mwh,
    max(h.demand_mwh)                                                        as peak_demand_mwh,
    sum(h.demand_mwh) / any_value(t.all_zones_mwh)                           as share_of_energy,
    -- MWh of extra zone demand per +1°F of local temperature when it's hot...
    regr_slope(h.demand_mwh, h.zone_temp_f) filter (where h.zone_temp_f >= 75)  as heat_slope_mwh_per_f,
    -- ...as a % of the zone's own average, so big and small zones compare fairly.
    100 * regr_slope(h.demand_mwh, h.zone_temp_f) filter (where h.zone_temp_f >= 75)
        / avg(h.demand_mwh)                                                  as heat_slope_pct_per_f,
    regr_slope(h.demand_mwh, h.zone_temp_f) filter (where h.zone_temp_f <= 50)  as cold_slope_mwh_per_f,
    regr_r2(h.demand_mwh, h.zone_temp_f) filter (where h.zone_temp_f >= 75)     as heat_r2
from hourly h
cross join totals t
group by h.zone_code
