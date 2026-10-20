"""Next-day hourly demand forecast for ERCOT, backtested month by month.

Model: gradient-boosted trees (scikit-learn HistGradientBoostingRegressor) on calendar, weather and
lagged-demand features. Only information available the day before is used for the lags (demand 2 days
and 7 days earlier at the same hour), so the model could run each morning for the next day.

Backtest (walk-forward): for each month, train on everything before that month and predict it. Each
month's predictions are written as one Parquet file in the lake, like the ingestion layer:
    data/raw/model_demand_forecast_hourly/year=YYYY/month=MM/data.parquet
dbt then compares them with ERCOT's own day-ahead forecast (EIA "DF") and actual demand.

Weather: this version uses OBSERVED temperatures for the forecast day, i.e. a perfect weather forecast.
That is a best case; roadmap item t2r scores it again with real day-ahead weather forecasts.

Usage (after `python -m src.run_dbt`):
    python -m src.forecast                 # predict new and recent months (older months are kept)
    python -m src.forecast --force         # re-run the whole backtest
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from src.ingestion import config
from src.ingestion.common import write_monthly

log = logging.getLogger("forecast")
DATASET = "model_demand_forecast_hourly"
MODEL_VERSION = "hgb-v1"
MIN_TRAIN_DAYS = 90          # don't predict a month until there are 3 months of history
RECENT_DAYS = 45             # months ending within this window are always re-predicted
FEATURES = ["hour", "dow", "is_business_day", "is_holiday", "doy_sin", "doy_cos",
            "temp_f", "cooling_dh", "heating_dh", "humidity_pct", "demand_lag48", "demand_lag168"]

QUERY = f"""
    select g.period_utc, g.period_local, g.demand_mwh, g.avg_temp_f, g.avg_humidity_pct,
           g.hour_local, d.iso_day_of_week, d.is_business_day, d.is_holiday, dayofyear(d.date_day) as doy,
           -- Winter Storm Uri: delivered demand was cut by blackouts, so it isn't real demand. Don't learn from it.
           g.period_local >= timestamp '2021-02-15 01:00:00' and g.period_local < timestamp '2021-02-18 01:00:00'
               as is_load_shed
    from fct_grid_hourly g
    join dim_date d using (date_key)
    order by g.period_utc
"""


def load(con) -> pd.DataFrame:
    return con.sql(QUERY).df()


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add model features. Lags are taken on a complete hourly index, so a missing hour stays missing."""
    df = df.copy()
    df["period_utc"] = pd.to_datetime(df["period_utc"], utc=True)
    df = df.set_index("period_utc").sort_index()
    full = pd.date_range(df.index.min(), df.index.max(), freq="h", tz="UTC")
    demand = df["demand_mwh"].reindex(full)
    df["demand_lag48"] = demand.shift(48).reindex(df.index)     # same hour, 2 days earlier
    df["demand_lag168"] = demand.shift(168).reindex(df.index)   # same hour, 1 week earlier
    df["hour"] = df["hour_local"].astype(int)
    df["dow"] = df["iso_day_of_week"].astype(int)
    df["is_business_day"] = df["is_business_day"].astype(int)
    df["is_holiday"] = df["is_holiday"].astype(int)
    df["doy_sin"] = np.sin(2 * np.pi * df["doy"] / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * df["doy"] / 365.25)
    df["temp_f"] = df["avg_temp_f"]
    df["cooling_dh"] = (df["avg_temp_f"] - 65).clip(lower=0)
    df["heating_dh"] = (65 - df["avg_temp_f"]).clip(lower=0)
    df["humidity_pct"] = df["avg_humidity_pct"]
    # Backtest months are UTC months, matching the lake's monthly files (one file = one training run).
    df["month_start"] = df.index.tz_convert(None).to_period("M").to_timestamp()
    return df.reset_index(names="period_utc")


def new_model() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                         l2_regularization=1.0, random_state=0)


def backtest_month(df: pd.DataFrame, month_start: pd.Timestamp) -> pd.DataFrame:
    """Train on everything before `month_start`, predict that month."""
    train = df[(df["month_start"] < month_start) & df["demand_mwh"].notna() & ~df["is_load_shed"]]
    test = df[df["month_start"] == month_start]
    model = new_model().fit(train[FEATURES], train["demand_mwh"])
    return pd.DataFrame({
        "period_utc": test["period_utc"].reset_index(drop=True),
        "predicted_mwh": model.predict(test[FEATURES]).round(1),
        "model_version": MODEL_VERSION,
        "train_rows": len(train),
        "trained_through": train["period_utc"].max(),
        "created_at": datetime.now(timezone.utc),
    })


def months_to_predict(df: pd.DataFrame, force: bool = False) -> list[pd.Timestamp]:
    months = sorted(df["month_start"].unique())
    first_day = df["period_utc"].min().tz_convert(None)
    eligible = [pd.Timestamp(m) for m in months if pd.Timestamp(m) - first_day >= timedelta(days=MIN_TRAIN_DAYS)]
    if force:
        return eligible
    recent = pd.Timestamp.now() - timedelta(days=RECENT_DAYS)
    out = []
    for m in eligible:
        path = config.RAW_DIR / DATASET / f"year={m.year}" / f"month={m.month:02d}" / "data.parquet"
        month_end = m + pd.offsets.MonthEnd(1)
        current = path.exists() and pd.read_parquet(path, columns=["model_version"])["model_version"].eq(MODEL_VERSION).all()
        if not current or month_end >= recent:
            out.append(m)
    return out


def run(force: bool = False) -> int:
    db = config.DATA_DIR / "warehouse.duckdb"
    if not db.exists():
        raise SystemExit(f"{db} not found. Run `python -m src.run_dbt` first.")
    with duckdb.connect(str(db), read_only=True) as con:
        df = make_features(load(con))
    months = months_to_predict(df, force)
    log.info("Predicting %d month(s) with %s", len(months), MODEL_VERSION)
    total = 0
    for m in months:
        preds = backtest_month(df, m)
        write_monthly(preds, DATASET, "period_utc", config.RAW_DIR)
        total += len(preds)
        log.info("%s: %d hours predicted (trained on %d hours)", f"{m:%Y-%m}", len(preds), preds["train_rows"].iloc[0])
    log.info("Done: %d predictions", total)
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-run the whole backtest")
    run(force=ap.parse_args().force)


if __name__ == "__main__":
    main()
