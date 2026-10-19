-- One row per hour with demand, forecast and generation side by side.
select
    period_utc,
    max(case when series_type = 'D'  then value_mwh end) as demand_mwh,
    max(case when series_type = 'DF' then value_mwh end) as forecast_mwh,
    max(case when series_type = 'NG' then value_mwh end) as net_generation_mwh
from {{ ref('stg_eia__ercot_hourly') }}
group by period_utc
