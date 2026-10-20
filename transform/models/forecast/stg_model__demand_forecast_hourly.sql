-- Our model's hourly demand predictions; latest prediction per hour if a month was re-run.
with ranked as (
    select
        cast(period_utc as timestamptz)     as period_utc,
        cast(predicted_mwh as double)       as predicted_mwh,
        cast(predicted_fw_mwh as double)    as predicted_fw_mwh,
        cast(forecast_temp_f as double)     as forecast_temp_f,
        model_version,
        cast(train_rows as integer)         as train_rows,
        cast(trained_through as timestamptz) as trained_through,
        created_at,
        row_number() over (partition by period_utc order by created_at desc) as rn
    from {{ source('raw', 'model_demand_forecast_hourly') }}
)

select period_utc, predicted_mwh, predicted_fw_mwh, forecast_temp_f, model_version, train_rows, trained_through, created_at
from ranked
where rn = 1
