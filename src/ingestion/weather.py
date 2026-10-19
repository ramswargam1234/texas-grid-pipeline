"""Ingest hourly historical weather for major Texas metros from Open-Meteo (no API key).

Writes: data/raw/weather_hourly/year=YYYY/month=MM/data.parquet

Usage:
    python -m src.ingestion.weather --start 2021-01-01 --end 2026-10-13   # backfill
    python -m src.ingestion.weather --days 14                              # recent refresh
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

from src.ingestion import config
from src.ingestion.common import get_json, write_monthly

log = logging.getLogger("weather")
DATASET = "weather_hourly"
ARCHIVE_LAG_DAYS = 6  # the archive API trails real time by a few days


def fetch_city(city: str, lat: float, lon: float, start: date, end: date,
               session: requests.Session | None = None) -> pd.DataFrame:
    http = session or requests.Session()
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(config.WEATHER_VARS),
        "temperature_unit": "fahrenheit",
        "timezone": "GMT",  # UTC, so it joins cleanly with EIA hourly data
    }
    return to_frame(get_json(http, config.WEATHER_URL, params, config.REQUEST_TIMEOUT), city)


def to_frame(body: dict, city: str) -> pd.DataFrame:
    hourly = body.get("hourly", {})
    df = pd.DataFrame(hourly)
    if df.empty:
        return df
    df = df.rename(columns={
        "time": "period_utc",
        "temperature_2m": "temp_f",
        "apparent_temperature": "feels_like_f",
        "relative_humidity_2m": "humidity_pct",
    })
    df["period_utc"] = pd.to_datetime(df["period_utc"], utc=True)
    df.insert(1, "city", city)
    df["ingested_at"] = datetime.now(timezone.utc)
    return df


def year_chunks(start: date, end: date) -> list[tuple[date, date]]:
    chunks, cur = [], start
    while cur <= end:
        chunk_end = min(end, date(cur.year, 12, 31))
        chunks.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return chunks


def run(start: date, end: date) -> int:
    # Each month is one file that gets overwritten, so always load whole months.
    start = start.replace(day=1)
    frames = []
    with requests.Session() as s:
        for city, (lat, lon) in config.CITIES.items():
            for c_start, c_end in year_chunks(start, end):
                log.info("%s %s -> %s", city, c_start, c_end)
                frames.append(fetch_city(city, lat, lon, c_start, c_end, session=s))
                time.sleep(0.5)  # stay well inside free-tier fair use
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not df.empty:
        df = df.dropna(subset=["temp_f"])
        write_monthly(df, DATASET, "period_utc", config.RAW_DIR)
    log.info("Done: %d rows", len(df))
    return len(df)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat)
    ap.add_argument("--end", type=date.fromisoformat)
    ap.add_argument("--days", type=int, default=14, help="if no --start, load the last N days")
    a = ap.parse_args()
    end = a.end or date.today() - timedelta(days=ARCHIVE_LAG_DAYS)
    start = a.start or end - timedelta(days=a.days)
    run(start, end)


if __name__ == "__main__":
    main()
