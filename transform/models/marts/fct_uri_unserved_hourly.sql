-- Winter Storm Uri (Feb 2021): how much demand went unserved during ERCOT's rolling blackouts?
--
-- Measured demand during load shed is what the grid could deliver, not what people needed.
-- We estimate the missing demand two independent ways:
--   1. Forecast gap:  ERCOT's day-ahead forecast minus actual demand.
--   2. Weather model: what demand "should" have been at that temperature: a linear model with one
--                     temperature slope and a separate baseline per hour of day, fit on cold winter
--                     hours from every other winter in the data.
-- Unserved energy is counted only inside the official load-shed window (see dbt_project.yml vars).

with hourly as (
    select * from {{ ref('fct_grid_hourly') }}
),

training_rows as (
    -- Cold-weather hours from every winter, excluding the storm itself.
    select
        hour_local,
        demand_mwh,
        avg_temp_f,
        avg(demand_mwh) over (partition by hour_local) as hour_mean_demand,
        avg(avg_temp_f) over (partition by hour_local) as hour_mean_temp
    from hourly
    where month_local in (12, 1, 2)
      and avg_temp_f < 50
      and demand_mwh is not null
      and avg_temp_f is not null
      and not (period_local >= '{{ var("uri_window_start") }}'
               and period_local <  '{{ var("uri_window_end") }}')
),

slope as (
    -- One temperature slope shared by all hours (hour-of-day fixed effects):
    -- regress demand on temperature after removing each hour's own average.
    select
        regr_slope(demand_mwh - hour_mean_demand, avg_temp_f - hour_mean_temp) as slope_mwh_per_f,
        regr_r2(demand_mwh - hour_mean_demand, avg_temp_f - hour_mean_temp)    as r2,
        count(*)                                                               as training_hours,
        min(avg_temp_f)                                                        as coldest_training_temp_f
    from training_rows
),

training as (
    -- Each hour keeps its own baseline; the line passes through that hour's averages.
    select
        h.hour_local,
        h.hour_mean_demand - s.slope_mwh_per_f * h.hour_mean_temp as intercept_mwh,
        s.slope_mwh_per_f,
        s.r2,
        s.training_hours,
        s.coldest_training_temp_f
    from (select distinct hour_local, hour_mean_demand, hour_mean_temp from training_rows) h
    cross join slope s
),

event as (
    select
        h.period_local,
        h.period_utc,
        h.hour_local,
        h.demand_mwh,
        h.forecast_mwh,
        h.avg_temp_f,
        t.intercept_mwh + t.slope_mwh_per_f * h.avg_temp_f as weather_expected_mwh,
        t.r2                                               as model_r2,
        t.training_hours,
        t.coldest_training_temp_f,
        h.period_local >= '{{ var("uri_shed_start") }}'
            and h.period_local < '{{ var("uri_shed_end") }}' as is_load_shed
    from hourly h
    left join training t using (hour_local)
    where h.period_local >= '{{ var("uri_window_start") }}'
      and h.period_local <  '{{ var("uri_window_end") }}'
)

select
    *,
    case when is_load_shed then greatest(forecast_mwh - demand_mwh, 0) end         as unserved_vs_forecast_mwh,
    case when is_load_shed then greatest(weather_expected_mwh - demand_mwh, 0) end as unserved_vs_weather_mwh,
    -- Flags hours where the weather model is extrapolating beyond the coldest training hour.
    avg_temp_f < coldest_training_temp_f                                             as is_extrapolated
from event
