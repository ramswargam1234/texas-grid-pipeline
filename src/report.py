"""Print headline findings from the dbt warehouse.

Usage (after `dbt build`):
    python -m src.report
"""
from __future__ import annotations

import duckdb

from src.ingestion import config

DB_PATH = config.DATA_DIR / "warehouse.duckdb"


def q(con, sql: str):
    return con.sql(sql).fetchone()


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found. Run `dbt build` in transform/ first.")
    con = duckdb.connect(str(DB_PATH), read_only=True)

    rows_grid = q(con, "select count(*) from stg_eia__ercot_hourly")[0]
    rows_wx = q(con, "select count(*) from stg_weather__hourly")[0]
    hours, first, last = q(con, "select count(*), min(date_local), max(date_local) from fct_grid_hourly")

    peak_mwh, peak_ts, peak_temp = q(con, """
        select demand_mwh, period_local, avg_temp_f
        from fct_grid_hourly where demand_mwh is not null
        order by demand_mwh desc limit 1""")

    # Demand sensitivity to temperature, split into the cooling and heating regimes.
    cool_slope = q(con, "select regr_slope(demand_mwh, avg_temp_f) from fct_grid_hourly where avg_temp_f >= 75")[0]
    heat_slope = q(con, "select regr_slope(demand_mwh, avg_temp_f) from fct_grid_hourly where avg_temp_f <= 50")[0]
    hot_vs_mild = q(con, """
        select avg(case when avg_temp_f >= 95 then demand_mwh end)
             / avg(case when avg_temp_f between 65 and 75 then demand_mwh end)
        from fct_grid_hourly""")[0]

    mape = q(con, "select avg(abs_pct_error) from fct_grid_hourly")[0]
    peak_hour = q(con, """
        select peak_hour_local, count(*) as n from agg_grid_daily
        group by 1 order by n desc limit 1""")[0]
    missing = q(con, "select count(*) from dq_grid_missing_hours")[0]

    freeze = q(con, """
        select min(min_temp_f), max(peak_demand_mwh)
        from agg_grid_daily where date_local between '2021-02-13' and '2021-02-18'""")

    def fmt(x, spec=",.0f"):
        return "n/a" if x is None else format(x, spec)

    print("\n=== Texas Grid & Weather: headline findings ===")
    print(f"Coverage           : {first} -> {last}  ({hours:,} hours)")
    print(f"Rows modeled       : {rows_grid:,} grid + {rows_wx:,} weather = {rows_grid + rows_wx:,}")
    print(f"All-time peak      : {fmt(peak_mwh)} MWh at {peak_ts:%Y-%m-%d %H:00} CT (avg temp {fmt(peak_temp, '.0f')}°F)")
    print(f"Heat sensitivity   : +{fmt(cool_slope)} MWh per +1°F when avg temp >= 75°F")
    print(f"Cold sensitivity   : {fmt(heat_slope)} MWh per +1°F when avg temp <= 50°F (colder = more demand)")
    print(f"Hot vs mild hours  : demand {fmt(hot_vs_mild, '.2f')}x higher at >=95°F than at 65-75°F")
    print(f"Most common peak   : {peak_hour}:00 Central")
    print(f"Day-ahead forecast : {fmt(mape * 100 if mape else None, '.2f')}% mean absolute % error")
    print(f"Feb 2021 freeze    : low {fmt(freeze[0], '.0f')}°F, peak demand {fmt(freeze[1])} MWh (Feb 13-18)")
    uri = con.sql("select unserved_gwh_forecast, unserved_gwh_weather, max_hourly_gap_forecast_mwh, "
                  "extrapolated_hours, shed_hours from agg_uri_summary").fetchone()
    print(f"Uri unserved energy: ~{fmt(uri[0])} GWh (forecast gap) / ~{fmt(uri[1])} GWh (weather model) "
          f"over {uri[4]} load-shed hours")
    print(f"Uri max shortfall  : {fmt(uri[2])} MWh in one hour (forecast gap); "
          f"{uri[3]} hours colder than any training hour")
    print(f"Missing grid hours : {missing:,} (see dq_grid_missing_hours)")
    print()


if __name__ == "__main__":
    main()
