-- Daily summary (Central time): peak demand, when it happened, and the weather that day.
with hourly as (
    select * from {{ ref('fct_grid_hourly') }}
),

ranked as (
    select
        *,
        row_number() over (partition by date_local order by demand_mwh desc nulls last) as demand_rank
    from hourly
)

select
    date_local,
    max(demand_mwh)                                         as peak_demand_mwh,
    max(case when demand_rank = 1 then hour_local end)      as peak_hour_local,
    sum(demand_mwh)                                         as total_demand_mwh,
    avg(demand_mwh)                                         as avg_demand_mwh,
    max(max_temp_f)                                         as max_temp_f,
    min(min_temp_f)                                         as min_temp_f,
    avg(avg_temp_f)                                         as avg_temp_f,
    sum(cooling_degree_hours)                               as cooling_degree_hours,
    sum(heating_degree_hours)                               as heating_degree_hours,
    avg(abs_pct_error)                                      as forecast_mape,
    count(demand_mwh)                                       as hours_with_demand
from ranked
group by date_local
