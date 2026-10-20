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
    zones = con.sql("select zone_label, share_of_energy, heat_slope_pct_per_f from agg_zone_profile "
                    "order by heat_slope_pct_per_f desc").fetchall()
    if zones:
        top, bottom = zones[0], zones[-1]
        print(f"Zones              : {len(zones)}; most heat-sensitive {top[0]} (+{top[2]:.2f}%/°F), "
              f"least {bottom[0]} (+{bottom[2]:.2f}%/°F)")
    change = con.sql("""select zone_label, first_year, latest_year, first_pct_per_f, latest_pct_per_f, verdict
                         from rpt_zone_heat_change where verdict != 'Not enough years'
                         order by change_pct_points desc""").fetchall()
    if change:
        up, down = change[0], change[-1]
        clear = sum(1 for c in change if c[5] != "No clear change")
        print(f"Zone heat trend    : biggest rise {up[0]} {up[3]:+.2f} -> {up[4]:+.2f}%/°F ({up[1]}-{up[2]}, {up[5]}); "
              f"biggest drop {down[0]} {down[3]:+.2f} -> {down[4]:+.2f}%/°F ({down[5]}); "
              f"{clear} of {len(change)} zones changed beyond the 95% intervals")
    robust = con.sql("""select count(*) filter (where is_robust and verdict_as_reported in
                                                    ('More heat-sensitive', 'Less heat-sensitive')),
                               count(*) filter (where verdict_as_reported in
                                                    ('More heat-sensitive', 'Less heat-sensitive'))
                        from rpt_zone_heat_robustness""").fetchone()
    if robust and robust[1]:
        print(f"Trend robustness   : {robust[0]} of {robust[1]} zone changes hold when zones are reconciled to "
              f"ERCOT's total and when the 2025 issue year is left out (rpt_zone_heat_robustness)")
    revisions = con.sql("select count(*), coalesce(sum(abs(change_mwh)), 0) from rpt_eia_revisions").fetchone()
    print(f"EIA revisions seen : {revisions[0]:,} day/series changes ({fmt(revisions[1])} MWh moved), "
          "tracked by snp_eia_daily_totals")
    fuel = con.sql("select year, renewable_share, gas_share, coal_share from agg_fuel_yearly "
                   "where is_full_year order by year").fetchall()
    if fuel:
        f0, f1 = fuel[0], fuel[-1]
        print(f"Fuel mix (full yrs): renewables {f0[1]:.0%} ({f0[0]}) -> {f1[1]:.0%} ({f1[0]}); "
              f"coal {f0[3]:.0%} -> {f1[3]:.0%}")
    stress = con.sql("""select condition, share from agg_fuel_by_condition where fuel_key = 'NG'
                        order by condition""").fetchall()
    if stress:
        print("Gas share          : " + ", ".join(f"{c} {s:.0%}" for c, s in stress))
    hol = con.sql("""select holiday_name, median_change_pct from agg_holiday_summary
                     where days > 0 order by median_change_pct limit 3""").fetchall()
    if hol:
        print("Biggest holiday dip: " + ", ".join(f"{n} {c:+.1f}%" for n, c in hol)
              + " vs same weekday nearby (agg_holiday_summary)")
    has_fc = con.sql("select count(*) from information_schema.tables "
                     "where table_name = 'fct_forecast_hourly'").fetchone()[0]
    if has_fc:
        fc = con.sql("""select count(*), 100 * avg(model_abs_pct_error), 100 * avg(eia_abs_pct_error),
                               100 * avg(model_abs_pct_error) filter (where hour_local between 15 and 19),
                               100 * avg(eia_abs_pct_error)   filter (where hour_local between 15 and 19),
                               any_value(model_version)
                        from fct_forecast_hourly
                        where actual_mwh is not null and eia_forecast_mwh is not null
                          and model_forecast_mwh is not null and not is_load_shed""").fetchone()
        if fc and fc[0]:
            print(f"Our demand model   : {fc[5]} {fc[1]:.2f}% MAPE vs ERCOT {fc[2]:.2f}% over {fc[0]:,} backtest hours; "
                  f"3-7 PM peak {fc[3]:.2f}% vs {fc[4]:.2f}% (uses observed weather: best case until t2r)")
    print(f"Missing grid hours : {missing:,} (see dq_grid_missing_hours)")
    print()


if __name__ == "__main__":
    main()
