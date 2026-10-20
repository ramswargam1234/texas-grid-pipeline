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

Weather: every hour is predicted twice by the same trained model:
  predicted_mwh     with the OBSERVED weather of that hour (a perfect weather forecast: the model's own error)
  predicted_fw_mwh  with the DAY-AHEAD weather forecast (GFS, issued 24 hours earlier; what a forecaster knew)
The difference between the two errors is the part caused by the weather forecast being wrong.
The model is always trained on observed weather; only the inputs at prediction time change.

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
WEATHER_COLS = ["temp_f", "cooling_dh", "heating_dh", "humidity_pct", *[f"temp_{c}" for c in CITIES]]


def load_weather_forecast() -> pd.DataFrame:
    """Day-ahead weather forecasts from the lake (src/ingestion/weather_forecast), one column per city."""
    path = config.RAW_DIR / "weather_forecast_hourly"
    if not any(path.glob("*/*/*.parquet")):
        log.warning("No weather forecasts in %s: scoring with observed weather only", path)
        return pd.DataFrame()
    wx = duckdb.sql(f"""
        select period_utc, city, forecast_temp_f, forecast_humidity_pct
        from read_parquet('{path.as_posix()}/*/*/*.parquet', hive_partitioning = true)
        qualify row_number() over (partition by period_utc, city order by ingested_at desc) = 1
    """).df()
    temp = wx.pivot_table(index="period_utc", columns="city", values="forecast_temp_f")
    hum = wx.pivot_table(index="period_utc", columns="city", values="forecast_humidity_pct")
    temp.columns = [f"fc_temp_{c}" for c in temp.columns]
    hum.columns = [f"fc_hum_{c}" for c in hum.columns]
    out = temp.join(hum)
    out.index = pd.to_datetime(out.index, utc=True)
    return out


def load(con) -> pd.DataFrame:
    df = con.sql(QUERY).df()
    cities = con.sql(CITY_QUERY).df().pivot_table(index="period_utc", columns="city", values="temp_f")
    cities.columns = [f"temp_{c}" for c in cities.columns]
    return df.merge(cities, left_on="period_utc", right_index=True, how="left")


def make_features(df: pd.DataFrame, weather_forecast: pd.DataFrame | None = None) -> pd.DataFrame:
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
    # The same weather features, computed from the day-ahead forecast instead of observations.
    wf = weather_forecast if weather_forecast is not None else pd.DataFrame()
    for c in CITIES:
        df[f"fc_temp_{c}"] = wf[f"fc_temp_{c}"].reindex(df.index) if f"fc_temp_{c}" in wf else np.nan
        df[f"fc_hum_{c}"] = wf[f"fc_hum_{c}"].reindex(df.index) if f"fc_hum_{c}" in wf else np.nan
    metros = [f"fc_temp_{c}" for c in config.METRO_CITIES]
    df["fc_available"] = df[metros].notna().all(axis=1)
    df["fc_temp_f"] = df[metros].mean(axis=1)
    df["fc_humidity_pct"] = df[[f"fc_hum_{c}" for c in config.METRO_CITIES]].mean(axis=1)
    # Backtest months are UTC months, matching the lake's monthly files (one file = one training run).
    df["month_start"] = df.index.tz_convert(None).to_period("M").to_timestamp()
    return df.reset_index(names="period_utc")


def new_model() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                         l2_regularization=1.0, random_state=0)


def with_forecast_weather(test: pd.DataFrame) -> pd.DataFrame:
    """Swap observed weather features for their day-ahead forecast versions."""
    x = test.copy()
    x["temp_f"] = x["fc_temp_f"]
    x["cooling_dh"] = (x["fc_temp_f"] - 65).clip(lower=0)
    x["heating_dh"] = (65 - x["fc_temp_f"]).clip(lower=0)
    x["humidity_pct"] = x["fc_humidity_pct"]
    for c in CITIES:
        x[f"temp_{c}"] = x[f"fc_temp_{c}"]
    return x


def backtest_month(df: pd.DataFrame, month_start: pd.Timestamp, model: str = DEFAULT_MODEL) -> pd.DataFrame:
    """Train on everything before `month_start`, predict that month."""
    train = df[(df["month_start"] < month_start) & df["demand_mwh"].notna() & ~df["is_load_shed"]]
    test = df[df["month_start"] == month_start]
    test_fw = with_forecast_weather(test)
    if model == "v1":
        fitted = new_model().fit(train[FEATURES], train["demand_mwh"])
        predicted = fitted.predict(test[FEATURES])
        predicted_fw = fitted.predict(test_fw[FEATURES])
    else:
        train = train[train["level_mwh"].notna()]
        fitted = new_model().fit(train[FEATURES_V2], train["ratio_target"])
        predicted = fitted.predict(test[FEATURES_V2]) * test["level_mwh"].to_numpy()
        predicted_fw = fitted.predict(test_fw[FEATURES_V2]) * test["level_mwh"].to_numpy()
    predicted_fw = np.where(test["fc_available"].to_numpy(), predicted_fw, np.nan)  # no forecast, no score
    return pd.DataFrame({
        "period_utc": test["period_utc"].reset_index(drop=True),
        "predicted_mwh": np.round(predicted, 1),
        "predicted_fw_mwh": np.round(predicted_fw, 1),
        "forecast_temp_f": test["fc_temp_f"].round(1).reset_index(drop=True),
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
        if not path.exists() or month_end >= recent:
            out.append(m)
            continue
        old = pd.read_parquet(path)
        fc_hours = int(df.loc[df["month_start"] == m, "fc_available"].sum())
        current = (old["model_version"].eq(version).all() and "predicted_fw_mwh" in old
                   and old["predicted_fw_mwh"].notna().sum() >= fc_hours)  # new weather forecasts arrived
        if not current:
            out.append(m)
    return out


def run(force: bool = False, model: str = DEFAULT_MODEL) -> int:
    db = config.DATA_DIR / "warehouse.duckdb"
    if not db.exists():
        raise SystemExit(f"{db} not found. Run `python -m src.run_dbt` first.")
    with duckdb.connect(str(db), read_only=True) as con:
        df = make_features(load(con), load_weather_forecast())
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
