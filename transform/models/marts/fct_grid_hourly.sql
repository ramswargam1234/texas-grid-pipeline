-- Core fact table: one row per hour, Texas grid joined to Texas weather.
-- Local (Central) time columns are added because grid peaks follow local daily routines.
with grid as (
    select * from {{ ref('int_grid__hourly_pivoted') }}
),

weather as (
    select * from {{ ref('int_weather__texas_hourly') }}
),

joined as (
    select
        g.period_utc,
        (g.period_utc at time zone 'America/Chicago')         as period_local,
        g.demand_mwh,
        g.forecast_mwh,
        g.net_generation_mwh,
        g.demand_mwh - g.forecast_mwh                          as forecast_error_mwh,
        abs(g.demand_mwh - g.forecast_mwh)
            / nullif(g.demand_mwh, 0)                          as abs_pct_error,
        w.avg_temp_f,
        w.max_temp_f,
        w.min_temp_f,
        w.avg_feels_like_f,
        w.avg_humidity_pct,
        w.cooling_degree_hours,
        w.heating_degree_hours,
        w.dallas_temp_f,
        w.houston_temp_f,
        w.austin_temp_f,
        w.san_antonio_temp_f
    from grid g
    left join weather w using (period_utc)
)

select
    *,
    cast(period_local as date)                     as date_local,
    extract('hour' from period_local)              as hour_local,
    dayname(period_local)                          as day_of_week,
    extract('isodow' from period_local) in (6, 7)  as is_weekend,
    extract('month' from period_local)             as month_local,
    extract('year' from period_local)              as year_local
from joined
