-- Fuel shares under three grid conditions. Which sources carry the grid when demand is highest,
-- and what was left running during Winter Storm Uri's rolling blackouts?
with fuel as (
    select period_utc, period_local, fuel_key, fuel_label, fuel_group, greatest(generation_mwh, 0) as mwh
    from {{ ref('fct_fuel_hourly') }}
),

demand as (
    select period_utc, demand_mwh,
           percent_rank() over (partition by year_local order by demand_mwh) as demand_pct_rank
    from {{ ref('fct_grid_hourly') }}
    where demand_mwh is not null
),

tagged as (
    select 'All hours' as condition, f.* from fuel f
    union all
    select 'Top 5% demand hours', f.* from fuel f
    join demand d using (period_utc)
    where d.demand_pct_rank >= 0.95
    union all
    select 'Uri load shed', f.* from fuel f
    where f.period_local >= timestamp '{{ var("uri_shed_start") }}'
      and f.period_local <  timestamp '{{ var("uri_shed_end") }}'
),

by_fuel as (
    select condition, fuel_key, any_value(fuel_label) as fuel_label, any_value(fuel_group) as fuel_group,
           count(distinct period_utc) as hours, sum(mwh) as mwh
    from tagged
    group by 1, 2
)

select
    condition, fuel_key, fuel_label, fuel_group,
    max(hours) over (partition by condition)                       as hours,
    mwh / nullif(max(hours) over (partition by condition), 0)      as avg_mw,
    mwh / nullif(sum(mwh) over (partition by condition), 0)        as share
from by_fuel
