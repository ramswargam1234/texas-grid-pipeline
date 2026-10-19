-- Demand vs. temperature in 5°F bands: the core "how much does weather drive load" answer.
select
    cast(floor(avg_temp_f / 5) * 5 as integer)   as temp_band_f,
    count(*)                                     as hours,
    avg(demand_mwh)                              as avg_demand_mwh,
    quantile_cont(demand_mwh, 0.5)               as median_demand_mwh,
    max(demand_mwh)                              as max_demand_mwh
from {{ ref('fct_grid_hourly') }}
where demand_mwh is not null
  and avg_temp_f is not null
group by 1
order by 1
