"""Ingest archived DAY-AHEAD weather forecasts for the same 9 Texas cities (Open-Meteo Previous Runs API).

For every hour this stores the temperature and humidity that the GFS weather model forecast 24 hours
earlier. That is what a grid forecaster actually knew the day before, so the demand model can be scored
with it (src/forecast) and its error split into "the weather forecast was wrong" vs "the model was wrong".

Writes: data/raw/weather_forecast_hourly/year=YYYY/month=MM/data.parquet

Usage:
    python -m src.ingestion.weather_forecast --start 2021-04-01   # backfill (skips months already loaded)
    python -m src.ingestion.weather_forecast --days 10            # recent refresh
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

from src.ingestion import config
from src.ingestion.common import get_json, month_ranges, write_monthly

log = logging.getLogger("weather_forecast")
DATASET = "weather_forecast_hourly"
LEAD = "previous_day1"  # forecast issued 24 hours before the hour it describes
VARS = {f"temperature_2m_{LEAD}": "forecast_temp_f", f"relative_humidity_2m_{LEAD}": "forecast_humidity_pct"}
COLUMNS = ["period_utc", "city", "forecast_temp_f", "forecast_humidity_pct", "lead_hours", "weather_model"]


def fetch_city(city: str, lat: float, lon: float, start: date, end: date,
               session: requests.Session | None = None) -> pd.DataFrame:
    http = session or requests.Session()
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(VARS),
        "models": config.WEATHER_FORECAST_MODEL,
        "temperature_unit": "fahrenheit",
        "timezone": "GMT",  # UTC, so it joins cleanly with EIA hourly data
    }
    return to_frame(get_json(http, config.WEATHER_FORECAST_URL, params, config.REQUEST_TIMEOUT), city)


def to_frame(body: dict, city: str) -> pd.DataFrame:
    hourly = body.get("hourly", {})
    if not hourly or "time" not in hourly:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(hourly).rename(columns={"time": "period_utc", **VARS})
    for col in VARS.values():
        if col not in df:
            df[col] = None
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    df["period_utc"] = pd.to_datetime(df["period_utc"], utc=True)
    df.insert(1, "city", city)
    df["lead_hours"] = 24
    df["weather_model"] = config.WEATHER_FORECAST_MODEL
    df["ingested_at"] = datetime.now(timezone.utc)
    return df.dropna(subset=["forecast_temp_f"])


def month_path(m_start: date):
    return config.RAW_DIR / DATASET / f"year={m_start.year}" / f"month={m_start.month:02d}" / "data.parquet"


def run(start: date, end: date, force: bool = False) -> int:
    start = max(start.replace(day=1), date.fromisoformat(config.WEATHER_FORECAST_START))
    recent = date.today() - timedelta(days=45)
    total = 0
    with requests.Session() as s:
        for m_start, m_end in month_ranges(start, end):
            if not force and m_end < recent and month_path(m_start).exists():
                log.info("%s already loaded, skipping (use --force to reload)", f"{m_start:%Y-%m}")
                continue
            frames = []
            for city, (lat, lon) in config.CITIES.items():
                frames.append(fetch_city(city, lat, lon, m_start, m_end, session=s))
                time.sleep(0.3)  # stay well inside the free tier's fair use
            df = pd.concat(frames, ignore_index=True)
            if df.empty:
                log.warning("%s: no forecast data returned", f"{m_start:%Y-%m}")
                continue
            write_monthly(df, DATASET, "period_utc", config.RAW_DIR)
            total += len(df)
            log.info("%s: %d city-hours", f"{m_start:%Y-%m}", len(df))
    log.info("Done: %d rows", total)
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat)
    ap.add_argument("--end", type=date.fromisoformat)
    ap.add_argument("--days", type=int, default=10, help="if no --start, load the last N days")
    ap.add_argument("--force", action="store_true", help="reload months that already exist")
    a = ap.parse_args()
    end = a.end or date.today()
    start = a.start or end - timedelta(days=a.days)
    run(start, end, force=a.force)


if __name__ == "__main__":
    main()
