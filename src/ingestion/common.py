"""Shared helpers: month ranges and idempotent Parquet writes."""
from __future__ import annotations

import logging
import re
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)


RETRY_STATUSES = {429, 500, 502, 503, 504}


def _redact(url: str) -> str:
    """Hide API keys in URLs before they reach logs or error messages."""
    return re.sub(r"(api_key|apikey)=[^&]+", r"\1=***", url or "")


def get_json(http: requests.Session, url: str, params: dict, timeout: int,
             retries: int = 5, backoff: float = 2.0, sleep=time.sleep) -> dict:
    """GET with retries + exponential backoff on timeouts, 429 and 5xx errors."""
    for attempt in range(1, retries + 1):
        try:
            resp = http.get(url, params=params, timeout=timeout)
            status = getattr(resp, "status_code", 200)
            if status in RETRY_STATUSES:
                raise requests.HTTPError(f"HTTP {status}")
            if status >= 400:  # other client errors (bad key, bad params): don't retry
                raise RuntimeError(f"HTTP {status} from {_redact(getattr(resp, 'url', url))}")
            return resp.json()
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            if attempt == retries:
                raise RuntimeError(f"Gave up after {retries} attempts: {exc}") from None
            wait = backoff ** attempt
            log.warning("Attempt %d/%d failed (%s), retrying in %.0fs", attempt, retries, exc, wait)
            sleep(wait)


def month_ranges(start: date, end: date) -> list[tuple[date, date]]:
    """Split [start, end] into calendar-month chunks (inclusive)."""
    chunks = []
    cur = start
    while cur <= end:
        nxt = (pd.Timestamp(cur) + pd.offsets.MonthBegin(1)).date()
        chunks.append((cur, min(end, nxt - pd.Timedelta(days=1))))
        cur = nxt
    return chunks


def write_monthly(df: pd.DataFrame, dataset: str, ts_col: str, base: Path) -> list[Path]:
    """Write one Parquet file per month: <base>/<dataset>/year=YYYY/month=MM/data.parquet.

    Re-running for the same month overwrites that file, so loads are idempotent
    (safe to re-run backfills without creating duplicates).
    """
    if df.empty:
        log.warning("%s: no rows to write", dataset)
        return []
    paths = []
    keys = df[ts_col].dt.tz_convert(None).dt.to_period("M")  # partition by UTC month
    for period, part in df.groupby(keys):
        out_dir = base / dataset / f"year={period.year}" / f"month={period.month:02d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "data.parquet"
        part.sort_values(ts_col).to_parquet(path, index=False)
        paths.append(path)
        log.info("%s %s: %d rows -> %s", dataset, period, len(part), path)
    return paths
