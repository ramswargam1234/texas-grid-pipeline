-- One row per hour: actual demand, ERCOT's day-ahead forecast (EIA "DF") and our model's forecast.
-- Uri load-shed hours are flagged: actual demand there was cut by blackouts, so no forecast can be scored.
select
    g.period_utc,
    g.date_key,
    g.period_local,
    g.date_local,
    g.hour_local,
    g.demand_mwh                                                   as actual_mwh,
    g.forecast_mwh                                                 as eia_forecast_mwh,
    m.predicted_mwh                                                as model_forecast_mwh,
    m.model_version,
    g.forecast_mwh - g.demand_mwh                                  as eia_error_mwh,
    m.predicted_mwh - g.demand_mwh                                 as model_error_mwh,
    abs(g.forecast_mwh - g.demand_mwh) / nullif(g.demand_mwh, 0)   as eia_abs_pct_error,
    abs(m.predicted_mwh - g.demand_mwh) / nullif(g.demand_mwh, 0)  as model_abs_pct_error,
    g.period_local >= timestamp '{{ var("uri_shed_start") }}'
        and g.period_local < timestamp '{{ var("uri_shed_end") }}' as is_load_shed
from {{ ref('fct_grid_hourly') }} g
join {{ ref('stg_model__demand_forecast_hourly') }} m using (period_utc)
