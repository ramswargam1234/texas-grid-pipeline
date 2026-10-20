"""Generate a small, deterministic, synthetic data lake for CI and local testing.

Writes the same Parquet layout the real ingestion produces (data/raw/...), using the real
ingestion parsers, so `dbt build` can run end to end without API keys or network access.
The numbers are made up: plausible seasonal shapes plus a simulated Feb 2021 cold snap
with 15 GW of load shed, so the Winter Storm Uri models have something to measure.

Usage:
    python -m src.sample_data
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.ingestion import config, eia_demand, eia_zones, weather
from src.ingestion.common import write_monthly

log = logging.getLogger("sample_data")

START, END = "2020-12-01", "2021-08-31 23:00"
SHED_START, SHED_END = pd.Timestamp("2021-02-15 01:00"), pd.Timestamp("2021-02-18 01:00")
SIMULATED_SHED_MW = 15_000
# Zone code -> (share of ERCOT load, temperature offset of its reference city in °F).
ZONES = {"COAS": (0.27, 2), "NCEN": (0.30, 0), "SCEN": (0.15, 2), "FWES": (0.08, -1),
         "SOUT": (0.08, 4), "EAST": (0.04, -1), "NRTH": (0.03, -3), "WEST": (0.05, -2)}


def build(seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    hours = pd.date_range(START, END, freq="h", tz="UTC")
    local = hours.tz_convert("America/Chicago").tz_localize(None)
    doy, hr = hours.dayofyear.to_numpy(), local.hour.to_numpy()

    # Temperature (°F): warm summers, cool winters, a daily cycle, and a deep Feb 2021 freeze.
    base = 72 + 22 * np.cos(2 * np.pi * (doy - 200) / 365) + 8 * np.sin(2 * np.pi * (hr - 9) / 24)
    base = np.where(hours.month.to_numpy() <= 2, base - 15, base)
    freeze = (local >= pd.Timestamp("2021-02-13")) & (local < pd.Timestamp("2021-02-19"))
    base = np.where(freeze, base - 30, base)

    wx = []
    for city, offset in [("dallas", 0), ("houston", 2), ("austin", 1), ("san_antonio", 3),
                         ("midland", -1), ("abilene", -2), ("wichita_falls", -3), ("tyler", -1),
                         ("corpus_christi", 4)]:
        t = base + offset + rng.normal(0, 2, len(hours))
        body = {"hourly": {"time": hours.strftime("%Y-%m-%dT%H:%M").tolist(),
                           "temperature_2m": t.round(1).tolist(),
                           "apparent_temperature": (t + 3).round(1).tolist(),
                           "relative_humidity_2m": rng.integers(30, 90, len(hours)).tolist()}}
        wx.append(weather.to_frame(body, city))

    # Demand (MWh): U-shaped in temperature plus a daily cycle; load shed during the storm.
    avg_t = base + 1.5
    true_demand = (42_000 + 900 * np.clip(avg_t - 70, 0, None) + 1_100 * np.clip(55 - avg_t, 0, None)
                   + 3_000 * np.sin(2 * np.pi * (hr - 11) / 24) + rng.normal(0, 800, len(hours)))
    shed = (local >= SHED_START) & (local < SHED_END)
    actual = np.where(shed, true_demand - SIMULATED_SHED_MW, true_demand)
    forecast = true_demand * (1 + rng.normal(0, 0.01, len(hours)))

    rows = []
    for i, ts in enumerate(hours):
        period = ts.strftime("%Y-%m-%dT%H")
        for typ, val in (("D", actual[i]), ("DF", forecast[i]), ("NG", actual[i] * 0.98)):
            rows.append({"period": period, "respondent": "ERCO", "type": typ, "type-name": typ,
                         "value": f"{val:.0f}", "value-units": "megawatthours"})
    zone_rows = []
    for i, ts in enumerate(hours):
        period = ts.strftime("%Y-%m-%dT%H")
        for code, (share, _) in ZONES.items():
            zone_rows.append({"period": period, "parent": "ERCO", "subba": code, "subba-name": code,
                              "value": f"{actual[i] * share:.0f}", "value-units": "megawatthours"})
    return pd.concat(wx, ignore_index=True), eia_demand.to_frame(rows), eia_zones.to_frame(zone_rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    wx, grid, zones = build()
    write_monthly(wx, weather.DATASET, "period_utc", config.RAW_DIR)
    write_monthly(grid, eia_demand.DATASET, "period_utc", config.RAW_DIR)
    write_monthly(zones, eia_zones.DATASET, "period_utc", config.RAW_DIR)
    log.info("Sample lake written to %s (%d grid rows, %d weather rows)", config.RAW_DIR, len(grid), len(wx))


if __name__ == "__main__":
    main()
