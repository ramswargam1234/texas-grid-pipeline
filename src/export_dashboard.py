"""Export small, aggregated snapshots from the dbt warehouse for the public dashboard.

The full warehouse stays local; only these summary CSVs (a few hundred KB) are
committed, so the hosted dashboard needs no database or credentials.

Usage (after dbt build):
    python -m src.export_dashboard
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import duckdb

from src.ingestion import config

log = logging.getLogger("export_dashboard")
DB_PATH = config.DATA_DIR / "warehouse.duckdb"
OUT_DIR = config.SNAPSHOT_DIR

FUEL_GROUP = """case fuel_key when 'WND' then 'Wind' when 'NG' then 'Natural gas' when 'NUC' then 'Nuclear'
                       when 'SUN' then 'Solar' when 'SNB' then 'Solar' when 'COL' then 'Coal'
                       else 'Other' end"""
MANIFEST = config.PROJECT_ROOT / "transform" / "target" / "manifest.json"

QUERIES = {
    # One row per day: peak demand, weather, forecast accuracy.
    "daily": """
        select date_local, peak_demand_mwh, peak_hour_local, avg_demand_mwh,
               max_temp_f, min_temp_f, avg_temp_f, forecast_mape, hours_with_demand
        from agg_grid_daily
        where date_local is not null
        order by date_local
    """,
    # Demand by 5°F band of average Texas temperature.
    "by_temperature": """
        select temp_band_f, hours, avg_demand_mwh, median_demand_mwh, max_demand_mwh
        from agg_demand_by_temperature
        where hours >= 24          -- drop thin bands so averages are meaningful
        order by temp_band_f
    """,
    # Average demand by local hour x month (seasonal daily shape).
    "hour_by_month": """
        select month_local as month, hour_local as hour, avg(demand_mwh) as avg_demand_mwh
        from fct_grid_hourly
        where demand_mwh is not null
        group by 1, 2
        order by 1, 2
    """,
    # Day-ahead forecast accuracy per month.
    "forecast_monthly": """
        select date_trunc('month', date_local)::date as month,
               avg(abs_pct_error) * 100           as mape_pct,
               avg(forecast_error_mwh)            as mean_error_mwh
        from fct_grid_hourly
        where abs_pct_error is not null
        group by 1
        having count(*) >= 24 * 7      -- skip partial months at the edges of the range
        order by 1
    """,
    # Hourly detail for the February 2021 winter storm (Uri).
    "freeze_2021": """
        select period_local, demand_mwh, forecast_mwh, weather_expected_mwh, avg_temp_f, is_load_shed
        from fct_uri_unserved_hourly
        order by period_local
    """,
    # One row per ERCOT weather zone: share of energy and temperature sensitivity.
    "zones": """
        select zone_code, zone_label, hours, avg_demand_mwh, peak_demand_mwh, share_of_energy,
               heat_slope_mwh_per_f, heat_slope_pct_per_f, cold_slope_mwh_per_f, heat_r2
        from agg_zone_profile
        order by share_of_energy desc
    """,
    # Heat sensitivity per zone per year, with 95% confidence intervals (reliable years only).
    "zone_heat_trend": """
        select zone_code, zone_label, year, hot_days, slope_pct_per_f, ci_low_pct_per_f, ci_high_pct_per_f,
               slope_mwh_per_f
        from agg_zone_heat_trend
        where is_reliable
        order by zone_code, year
    """,
    # First vs latest year per zone, with a verdict that only calls a change when intervals don't overlap.
    "zone_heat_change": """
        select c.zone_code, c.zone_label, c.first_year, c.latest_year, c.first_pct_per_f, c.latest_pct_per_f,
               c.change_pct_points, c.verdict, r.is_robust, r.verdict_reconciled, r.verdict_issue_year_out
        from rpt_zone_heat_change c
        left join rpt_zone_heat_robustness r using (zone_code)
        order by c.change_pct_points desc
    """,
    # Typical demand change on each holiday vs nearby normal days.
    "holidays": """
        select holiday_name, is_nerc_holiday, days, median_change_pct, min_change_pct, max_change_pct,
               weather_distorted_days_left_out
        from agg_holiday_summary
        where days > 0
        order by median_change_pct
    """,
    # Monthly fuel mix, small fuels folded into "Other" so the chart stays readable.
    "fuel_monthly": f"""
        select month, {FUEL_GROUP} as fuel, sum(generation_gwh) as generation_gwh, sum(share) as share
        from agg_fuel_monthly
        where month in (select month from agg_fuel_monthly group by 1 having max(hours) >= 24 * 7)
                    -- skip partial months at the edges of the range
        group by 1, 2
        order by 1, 2
    """,
    # Fuel shares in all hours, peak-demand hours and the Uri blackouts.
    "fuel_by_condition": f"""
        select condition, {FUEL_GROUP} as fuel, sum(share) as share, sum(avg_mw) as avg_mw, max(hours) as hours
        from agg_fuel_by_condition
        group by 1, 2
        order by 1, 2
    """,
    # Data-quality: missing demand hours per month.
    "missing_by_month": """
        select date_trunc('month', date_local)::date as month, count(*) as missing_hours
        from dq_grid_missing_hours
        group by 1
        order by 1
    """,
}


def headline(con) -> dict:
    def one(sql):
        return con.sql(sql).fetchone()

    peak_mwh, peak_ts, peak_temp = one("""
        select demand_mwh, period_local, avg_temp_f from fct_grid_hourly
        where demand_mwh is not null order by demand_mwh desc limit 1""")
    hours, first, last = one("select count(*), min(date_local), max(date_local) from fct_grid_hourly")
    rows = one("select (select count(*) from stg_eia__ercot_hourly) + (select count(*) from stg_weather__hourly)")[0]
    heat = one("select regr_slope(demand_mwh, avg_temp_f) from fct_grid_hourly where avg_temp_f >= 75")[0]
    ratio = one("""select avg(case when avg_temp_f >= 95 then demand_mwh end)
                        / avg(case when avg_temp_f between 65 and 75 then demand_mwh end)
                   from fct_grid_hourly""")[0]
    mape = one("select avg(abs_pct_error) * 100 from fct_grid_hourly")[0]
    missing = one("select count(*) from dq_grid_missing_hours")[0]
    fuel = con.sql("""select year, renewable_share, carbon_free_share, gas_share, coal_share
                      from agg_fuel_yearly where is_full_year order by year""").df()
    fuel_years = fuel
    fuel_summary = {}
    if len(fuel_years):
        f0, f1 = fuel_years.iloc[0], fuel_years.iloc[-1]
        fuel_summary = {"first_year": int(f0["year"]), "latest_year": int(f1["year"]),
                        "renewable_first": float(f0["renewable_share"]),
                        "renewable_latest": float(f1["renewable_share"]),
                        "carbon_free_latest": float(f1["carbon_free_share"]),
                        "coal_first": float(f0["coal_share"]), "coal_latest": float(f1["coal_share"])}
    uri_df = con.sql("select * from agg_uri_summary").df()
    uri = {k: (None if v != v else v) for k, v in uri_df.iloc[0].to_dict().items()} if len(uri_df) else {}
    return {
        "peak_mwh": peak_mwh,
        "peak_time_local": peak_ts.isoformat() if peak_ts else None,
        "peak_avg_temp_f": peak_temp,
        "hours": hours,
        "first_date": str(first),
        "last_date": str(last),
        "rows_modeled": rows,
        "heat_slope_mwh_per_f": heat,
        "hot_vs_mild_ratio": ratio,
        "forecast_mape_pct": mape,
        "missing_hours": missing,
        "uri": uri,
        "fuel": fuel_summary,
        "is_demo": os.getenv("PIPELINE_DEMO") == "1",
        "forecast_model": forecast_summary(con),
        **test_counts(),
        "exported_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# Built only after the forecast stage (python -m src.forecast + run_dbt --stage forecast).
OPTIONAL_QUERIES = {
    "forecast_compare": """
        select month, hours, model_mape_pct, eia_mape_pct, model_peak_mape_pct, eia_peak_mape_pct,
               model_better_share, fw_hours, model_fw_mape_pct, model_obs_mape_fw_hours_pct,
               eia_mape_fw_hours_pct, weather_effect_pts, temp_forecast_mae_f
        from agg_forecast_accuracy_monthly
        where hours >= 24 * 7
        order by month
    """,
}


def has_table(con, name: str) -> bool:
    return con.sql(f"select count(*) from information_schema.tables where table_name = '{name}'").fetchone()[0] > 0


def forecast_summary(con) -> dict:
    """Backtest accuracy of our model vs ERCOT's forecast over all scored hours."""
    if not has_table(con, "fct_forecast_hourly"):
        return {}
    row = con.sql("""
        select count(*), 100 * avg(model_abs_pct_error), 100 * avg(eia_abs_pct_error),
               100 * avg(model_abs_pct_error) filter (where hour_local between 15 and 19),
               100 * avg(eia_abs_pct_error)   filter (where hour_local between 15 and 19),
               min(date_local), max(date_local), any_value(model_version)
        from fct_forecast_hourly
        where actual_mwh is not null and eia_forecast_mwh is not null and model_forecast_mwh is not null
          and not is_load_shed""").fetchone()
    if not row or not row[0]:
        return {}
    keys = ["hours", "model_mape_pct", "eia_mape_pct", "model_peak_mape_pct", "eia_peak_mape_pct",
            "first_date", "last_date", "model_version"]
    out = {k: (str(v) if k.endswith("date") else v) for k, v in zip(keys, row)}
    fw = con.sql("""
        select count(*), 100 * avg(model_fw_abs_pct_error), 100 * avg(model_abs_pct_error),
               100 * avg(eia_abs_pct_error), avg(abs(temp_forecast_error_f)), min(date_local)
        from fct_forecast_hourly
        where actual_mwh is not null and eia_forecast_mwh is not null and model_fw_forecast_mwh is not null
          and not is_load_shed""").fetchone()
    if fw and fw[0]:
        out["fw"] = {"hours": fw[0], "model_fw_mape_pct": fw[1], "model_obs_mape_pct": fw[2],
                     "eia_mape_pct": fw[3], "temp_mae_f": fw[4], "first_date": str(fw[5])}
    return out


def test_counts() -> dict:
    """Count dbt data tests and unit tests from the last build's manifest (shown on the dashboard)."""
    if not MANIFEST.exists():
        return {}
    m = json.loads(MANIFEST.read_text())
    data_tests = sum(1 for n in m.get("nodes", {}).values() if n.get("resource_type") == "test")
    return {"data_tests": data_tests, "unit_tests": len(m.get("unit_tests", {}))}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found. Run dbt build first.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    for name, sql in OPTIONAL_QUERIES.items():
        if not has_table(con, sql.split("from")[1].split()[0]):
            log.info("%s: skipped (run the forecast stage to build it)", name)
            continue
        con.sql(sql).df().to_csv(OUT_DIR / f"{name}.csv", index=False, float_format="%.6g")
        log.info("%s: written", name)
    for name, sql in QUERIES.items():
        df = con.sql(sql).df()
        df.to_csv(OUT_DIR / f"{name}.csv", index=False, float_format="%.6g")
        log.info("%s: %d rows", name, len(df))
    from src import freshness  # last dbt source-freshness results, if the check has run
    rows = [] if os.getenv("PIPELINE_DEMO") == "1" else freshness.load()  # demo data is old by design
    if rows:
        import pandas as pd
        pd.DataFrame(rows).to_csv(OUT_DIR / "freshness.csv", index=False)
        log.info("freshness: %d sources", len(rows))
    (OUT_DIR / "headline.json").write_text(json.dumps(headline(con), indent=2, default=str))
    log.info("Snapshot written to %s", OUT_DIR)


if __name__ == "__main__":
    main()
