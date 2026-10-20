-- Heat sensitivity per zone per year with 95% confidence intervals. Logic: macros/zone_heat.sql.
{{ zone_heat_trend(ref('fct_zone_hourly')) }}
