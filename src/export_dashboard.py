"""Export small, aggregated snapshots from the dbt warehouse for the public dashboard.

The full warehouse stays local; only these summary CSVs (a few hundred KB) are
committed, so the hosted dashboard needs no database or credentials.

Usage (after dbt build):
    python -m src.export_dashboard
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import duckdb

from src.ingestion import config

log = logging.getLogger("export_dashboard")
DB_PATH = config.DATA_DIR / "warehouse.duckdb"
OUT_DIR = config.PROJECT_ROOT / "dashboard" / "snapshot"

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
        "exported_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found. Run dbt build first.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    for name, sql in QUERIES.items():
        df = con.sql(sql).df()
        df.to_csv(OUT_DIR / f"{name}.csv", index=False, float_format="%.6g")
        log.info("%s: %d rows", name, len(df))
    (OUT_DIR / "headline.json").write_text(json.dumps(headline(con), indent=2, default=str))
    log.info("Snapshot written to %s", OUT_DIR)


if __name__ == "__main__":
    main()
