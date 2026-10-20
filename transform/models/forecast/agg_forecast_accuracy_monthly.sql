-- Monthly accuracy of our model vs ERCOT's day-ahead forecast, scored on exactly the same hours
-- (hours with actual demand and both forecasts, excluding Uri load shed).
select
    date_trunc('month', date_local)::date                          as month,
    count(*)                                                       as hours,
    round(100 * avg(model_abs_pct_error), 3)                       as model_mape_pct,
    round(100 * avg(eia_abs_pct_error), 3)                         as eia_mape_pct,
    round(avg(model_error_mwh), 1)                                 as model_bias_mwh,
    round(avg(eia_error_mwh), 1)                                   as eia_bias_mwh,
    -- Afternoon peak hours (3-7 PM Central), when forecast errors matter most for grid stress.
    round(100 * avg(model_abs_pct_error) filter (where hour_local between 15 and 19), 3) as model_peak_mape_pct,
    round(100 * avg(eia_abs_pct_error)   filter (where hour_local between 15 and 19), 3) as eia_peak_mape_pct,
    round(avg(case when model_abs_pct_error < eia_abs_pct_error then 1.0 else 0.0 end), 3) as model_better_share
from {{ ref('fct_forecast_hourly') }}
where actual_mwh is not null
  and eia_forecast_mwh is not null
  and model_forecast_mwh is not null
  and not is_load_shed
group by 1
