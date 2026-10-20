-- Our model's hourly demand predictions; latest prediction per hour if a month was re-run.
with ranked as (
    select
        cast(period_utc as timestamptz)     as period_utc,
        cast(predicted_mwh as double)       as predicted_mwh,
        model_version,
        cast(train_rows as integer)         as train_rows,
        cast(trained_through as timestamptz) as trained_through,
        created_at,
        row_number() over (partition by period_utc order by created_at desc) as rn
    from {{ source('raw', 'model_demand_forecast_hourly') }}
)

select period_utc, predicted_mwh, model_version, train_rows, trained_through, created_at
from ranked
where rn = 1
