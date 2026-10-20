"""Ingest hourly demand for each ERCOT weather zone from the EIA API (region-sub-ba-data).

ERCOT reports load for 8 weather zones (Coast, East, Far West, North, North Central,
South Central, Southern, West). The zone codes come straight from the API response,
so nothing here hard-codes them.

Writes: data/raw/eia_ercot_zone_hourly/year=YYYY/month=MM/data.parquet

Usage:
    python -m src.ingestion.eia_zones --start 2021-01-01    # backfill (skips months already loaded)
    python -m src.ingestion.eia_zones --days 7              # recent refresh
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

log = logging.getLogger("eia_zones")
DATASET = "eia_ercot_zone_hourly"
COLUMNS = ["period_utc", "parent", "zone_code", "zone_name", "demand_mwh", "units"]


def fetch_range(start: date, end: date, session: requests.Session | None = None) -> pd.DataFrame:
    """Fetch all zone-hour rows between start and end (inclusive), following pagination."""
    if not config.EIA_API_KEY:
        raise SystemExit("EIA_API_KEY is not set. Add it to your .env file.")
    http = session or requests.Session()
    params = {
        "api_key": config.EIA_API_KEY,
        "frequency": "hourly",  # UTC hours
        "data[0]": "value",
        "facets[parent][]": config.EIA_RESPONDENT,
        "start": f"{start:%Y-%m-%d}T00",
        "end": f"{end:%Y-%m-%d}T23",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": config.EIA_PAGE_SIZE,
    }
    rows, offset = [], 0
    while True:
        params["offset"] = offset
        body = get_json(http, config.EIA_ZONE_URL, params, config.REQUEST_TIMEOUT)["response"]
        page = body.get("data", [])
        rows.extend(page)
        total = int(body.get("total", len(rows)))
        offset += len(page)
        if not page or offset >= total:
            break
        time.sleep(0.2)
    return to_frame(rows)


def to_frame(rows: list[dict]) -> pd.DataFrame:
    """Clean raw API rows into a typed DataFrame."""
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "period_utc": pd.to_datetime(df["period"], format="%Y-%m-%dT%H", utc=True),
        "parent": df["parent"],
        "zone_code": df["subba"],
        "zone_name": df.get("subba-name"),
        "demand_mwh": pd.to_numeric(df["value"], errors="coerce").astype("float64"),  # API returns strings
        "units": df.get("value-units"),
    })
    out["ingested_at"] = datetime.now(timezone.utc)
    return out.drop_duplicates(["period_utc", "zone_code"])


def month_path(m_start: date):
    return config.RAW_DIR / DATASET / f"year={m_start.year}" / f"month={m_start.month:02d}" / "data.parquet"


def run(start: date, end: date, force: bool = False) -> int:
    # Each month is one file that gets overwritten, so always load whole months.
    start = start.replace(day=1)
    recent = date.today() - timedelta(days=45)  # recent months may still be revised: always reload
    total = 0
    with requests.Session() as s:
        for m_start, m_end in month_ranges(start, end):
            if not force and m_end < recent and month_path(m_start).exists():
                log.info("%s already loaded, skipping (use --force to reload)", f"{m_start:%Y-%m}")
                continue
            df = fetch_range(m_start, m_end, session=s)
            write_monthly(df, DATASET, "period_utc", config.RAW_DIR)
            total += len(df)
    log.info("Done: %d rows", total)
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat)
    ap.add_argument("--end", type=date.fromisoformat)
    ap.add_argument("--days", type=int, default=7, help="if no --start, load the last N days")
    ap.add_argument("--force", action="store_true", help="reload months that already exist")
    a = ap.parse_args()
    end = a.end or date.today()
    start = a.start or end - timedelta(days=a.days)
    run(start, end, force=a.force)


if __name__ == "__main__":
    main()
