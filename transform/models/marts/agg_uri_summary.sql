-- One-row summary of estimated unserved demand during Winter Storm Uri's load shed.
-- 1 MWh served over one hour = 1 MW average; GWh = MWh / 1,000.
select
    count(*) filter (where is_load_shed)                         as shed_hours,
    count(demand_mwh) filter (where is_load_shed)                as shed_hours_with_data,
    sum(unserved_vs_forecast_mwh) / 1000                         as unserved_gwh_forecast,
    sum(unserved_vs_weather_mwh) / 1000                          as unserved_gwh_weather,
    max(unserved_vs_forecast_mwh)                                as max_hourly_gap_forecast_mwh,
    max(unserved_vs_weather_mwh)                                 as max_hourly_gap_weather_mwh,
    max(forecast_mwh) filter (where is_load_shed)                as peak_forecast_mwh,
    max(weather_expected_mwh) filter (where is_load_shed)        as peak_weather_expected_mwh,
    max(demand_mwh) filter (where is_load_shed)                  as peak_actual_mwh,
    min(avg_temp_f) filter (where is_load_shed)                  as min_temp_f,
    avg(model_r2)                                                as weather_model_avg_r2,
    count(*) filter (where is_load_shed and is_extrapolated)     as extrapolated_hours
from {{ ref('fct_uri_unserved_hourly') }}
