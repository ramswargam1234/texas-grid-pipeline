"""Next-day hourly demand forecast for ERCOT, backtested month by month.

Model: gradient-boosted trees (scikit-learn HistGradientBoostingRegressor) on calendar, weather and
lagged-demand features. Only information available the day before is used for the lags (demand 2 days
and 7 days earlier at the same hour), so the model could run each morning for the next day.

Versions (pick with --model; the lake keeps the latest run):
  v1  predicts demand in MWh from the 4-metro average temperature.
  v2  (default) predicts demand RELATIVE TO ITS RECENT LEVEL (the average of the 14 days ending 2 days
      earlier) and sees all 9 cities' temperatures. Tree models can't predict values above anything they
      were trained on, and Texas demand grows every year; predicting a ratio lets the level carry the
      growth, so v1's steady under-forecasting goes away.

Backtest (walk-forward): for each month, train on everything before that month and predict it. Each
month's predictions are written as one Parquet file in the lake, like the ingestion layer:
    data/raw/model_demand_forecast_hourly/year=YYYY/month=MM/data.parquet
dbt then compares them with ERCOT's own day-ahead forecast (EIA "DF") and actual demand.

Weather: this version uses OBSERVED temperatures for the forecast day, i.e. a perfect weather forecast.
That is a best case; roadmap item t2r scores it again with real day-ahead weather forecasts.

Usage (after `python -m src.run_dbt`):
    python -m src.forecast                 # predict new and recent months (older months are kept)
    python -m src.forecast --force         # re-run the whole backtest
    python -m src.forecast --model v1      # the original model, for comparison
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
MODELS = {"v1": "hgb-v1", "v2": "hgb-v2"}
DEFAULT_MODEL = "v2"
MODEL_VERSION = MODELS[DEFAULT_MODEL]
CITIES = list(config.CITIES)
MIN_TRAIN_DAYS = 90          # don't predict a month until there are 3 months of history
RECENT_DAYS = 45             # months ending within this window are always re-predicted
CALENDAR = ["hour", "dow", "is_business_day", "is_holiday", "doy_sin", "doy_cos"]
FEATURES = CALENDAR + ["temp_f", "cooling_dh", "heating_dh", "humidity_pct", "demand_lag48", "demand_lag168"]
FEATURES_V2 = CALENDAR + ["temp_f", "cooling_dh", "heating_dh", "humidity_pct", "ratio_lag48", "ratio_lag168",
                          *[f"temp_{c}" for c in CITIES]]
LEVEL_HOURS = 14 * 24       # recent level = mean demand over 14 days...
LEVEL_GAP = 48              # ...ending 2 days before the hour being forecast

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


CITY_QUERY = "select period_utc, city, temp_f from stg_weather__hourly"


def load(con) -> pd.DataFrame:
    df = con.sql(QUERY).df()
    cities = con.sql(CITY_QUERY).df().pivot_table(index="period_utc", columns="city", values="temp_f")
    cities.columns = [f"temp_{c}" for c in cities.columns]
    return df.merge(cities, left_on="period_utc", right_index=True, how="left")


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add model features. Lags are taken on a complete hourly index, so a missing hour stays missing."""
    df = df.copy()
    df["period_utc"] = pd.to_datetime(df["period_utc"], utc=True)
    df = df.set_index("period_utc").sort_index()
    full = pd.date_range(df.index.min(), df.index.max(), freq="h", tz="UTC")
    demand = df["demand_mwh"].reindex(full)
    df["demand_lag48"] = demand.shift(48).reindex(df.index)     # same hour, 2 days earlier
    df["demand_lag168"] = demand.shift(168).reindex(df.index)   # same hour, 1 week earlier
    # v2: recent demand level, known the day before (mean of the 14 days ending 48 hours earlier).
    level = demand.shift(LEVEL_GAP).rolling(LEVEL_HOURS, min_periods=LEVEL_HOURS // 2).mean()
    df["level_mwh"] = level.reindex(df.index)
    df["ratio_lag48"] = df["demand_lag48"] / df["level_mwh"]
    df["ratio_lag168"] = df["demand_lag168"] / df["level_mwh"]
    df["ratio_target"] = df["demand_mwh"] / df["level_mwh"]
    for c in CITIES:
        if f"temp_{c}" not in df:
            df[f"temp_{c}"] = np.nan
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


def backtest_month(df: pd.DataFrame, month_start: pd.Timestamp, model: str = DEFAULT_MODEL) -> pd.DataFrame:
    """Train on everything before `month_start`, predict that month."""
    train = df[(df["month_start"] < month_start) & df["demand_mwh"].notna() & ~df["is_load_shed"]]
    test = df[df["month_start"] == month_start]
    if model == "v1":
        fitted = new_model().fit(train[FEATURES], train["demand_mwh"])
        predicted = fitted.predict(test[FEATURES])
    else:
        train = train[train["level_mwh"].notna()]
        fitted = new_model().fit(train[FEATURES_V2], train["ratio_target"])
        predicted = fitted.predict(test[FEATURES_V2]) * test["level_mwh"].to_numpy()
    return pd.DataFrame({
        "period_utc": test["period_utc"].reset_index(drop=True),
        "predicted_mwh": np.round(predicted, 1),
        "model_version": MODELS[model],
        "train_rows": len(train),
        "trained_through": train["period_utc"].max(),
        "created_at": datetime.now(timezone.utc),
    })


def months_to_predict(df: pd.DataFrame, force: bool = False, version: str = MODEL_VERSION) -> list[pd.Timestamp]:
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
        current = path.exists() and pd.read_parquet(path, columns=["model_version"])["model_version"].eq(version).all()
        if not current or month_end >= recent:
            out.append(m)
    return out


def run(force: bool = False, model: str = DEFAULT_MODEL) -> int:
    db = config.DATA_DIR / "warehouse.duckdb"
    if not db.exists():
        raise SystemExit(f"{db} not found. Run `python -m src.run_dbt` first.")
    with duckdb.connect(str(db), read_only=True) as con:
        df = make_features(load(con))
    months = months_to_predict(df, force, MODELS[model])
    log.info("Predicting %d month(s) with %s", len(months), MODELS[model])
    total = 0
    for m in months:
        preds = backtest_month(df, m, model)
        write_monthly(preds, DATASET, "period_utc", config.RAW_DIR)
        total += len(preds)
        log.info("%s: %d hours predicted (trained on %d hours)", f"{m:%Y-%m}", len(preds), preds["train_rows"].iloc[0])
    log.info("Done: %d predictions", total)
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-run the whole backtest")
    ap.add_argument("--model", choices=list(MODELS), default=DEFAULT_MODEL,
                    help="which model version to backtest (a different version re-runs every month)")
    a = ap.parse_args()
    run(force=a.force, model=a.model)


if __name__ == "__main__":
    main()
