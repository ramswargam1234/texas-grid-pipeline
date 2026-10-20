-- Monthly accuracy of our model vs ERCOT's day-ahead forecast.
-- Part 1 scores both on the same hours (actual, ERCOT and model forecast present; Uri load shed excluded).
-- Part 2 splits our model's error on the hours that also have a day-ahead weather forecast:
--   with observed weather  = the model's own error
--   with forecast weather  = what it would really have scored
--   weather_effect_pts     = the difference: error caused by the weather forecast being wrong
with scored as (
    select *
    from {{ ref('fct_forecast_hourly') }}
    where actual_mwh is not null
      and eia_forecast_mwh is not null
      and model_forecast_mwh is not null
      and not is_load_shed
)

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
    round(avg(case when model_abs_pct_error < eia_abs_pct_error then 1.0 else 0.0 end), 3) as model_better_share,
    -- Part 2: hours with a day-ahead weather forecast.
    count(model_fw_abs_pct_error)                                                       as fw_hours,
    round(100 * avg(model_fw_abs_pct_error), 3)                                         as model_fw_mape_pct,
    round(100 * avg(model_abs_pct_error) filter (where model_fw_abs_pct_error is not null), 3) as model_obs_mape_fw_hours_pct,
    round(100 * avg(eia_abs_pct_error)   filter (where model_fw_abs_pct_error is not null), 3) as eia_mape_fw_hours_pct,
    round(100 * (avg(model_fw_abs_pct_error)
                 - avg(model_abs_pct_error) filter (where model_fw_abs_pct_error is not null)), 3) as weather_effect_pts,
    round(avg(abs(temp_forecast_error_f)), 2)                                           as temp_forecast_mae_f
from scored
group by 1
