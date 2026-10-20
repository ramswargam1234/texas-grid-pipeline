-- Our model's predictions must stay in a physically plausible range for ERCOT (MWh per hour).
{{ config(tags = ['forecast']) }}
select period_utc, predicted_mwh
from {{ ref('stg_model__demand_forecast_hourly') }}
where predicted_mwh < 15000 or predicted_mwh > 130000
