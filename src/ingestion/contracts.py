"""Data contracts: what every dataset must look like before it is written to the lake.

`write_monthly` checks each batch against its contract (Pandera). A batch that breaks the contract is NOT
written: it is saved to data/quarantine/<dataset>/<timestamp>/ with a list of every failing check, and the
load stops with a clear error. Bad API data never reaches the lake, and nothing is lost for debugging.

What a contract checks:
  - required columns are present, with the right types (numbers coerced, timestamps in UTC)
  - keys are never null and never duplicated (one row per hour and series / zone / fuel / city)
  - values are physically plausible (a demand of 2 million MWh or a temperature of 300°F is a bug)
  - timestamps are real hours: not before 2015, not more than 2 days in the future
Extra columns are allowed, so EIA or Open-Meteo adding a field doesn't break the pipeline.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from src.ingestion import config

log = logging.getLogger("contracts")


class ContractViolation(Exception):
    """A batch broke its data contract and was quarantined instead of written."""


def _hour_column() -> pa.Column:
    return pa.Column(
        pd.DatetimeTZDtype("ns", "UTC"), coerce=True, nullable=False,
        checks=[
            pa.Check(lambda s: s >= pd.Timestamp("2015-01-01", tz="UTC"), error="hour before 2015"),
            pa.Check(lambda s: s <= pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=2), error="hour in the future"),
            pa.Check(lambda s: (s.dt.minute == 0) & (s.dt.second == 0), error="not on the hour"),
        ],
    )


def _num(lo: float, hi: float, nullable: bool = True) -> pa.Column:
    return pa.Column(float, coerce=True, nullable=nullable, checks=pa.Check.in_range(lo, hi))


# Storage fuels (batteries BAT, other energy storage OES, pumped/unspecified storage UES, pumped storage PS) report
# NEGATIVE net generation while charging, and the grid's storage fleet is growing fast: BAT already reached
# -11,553 MWh in 2026, so the old -10,000 limit rejected real data. Every other fuel (solar at night is the usual
# small negative) keeps the tight limit, so a negative gas or wind value is still caught as a bug.
STORAGE_FUELS = {"BAT", "OES", "UES", "PS"}
STORAGE_LIMIT_MWH = 30_000
DEFAULT_FUEL_FLOOR_MWH = 10_000


def _fuel_floor(code: str) -> float:
    return -(STORAGE_LIMIT_MWH if code in STORAGE_FUELS else DEFAULT_FUEL_FLOOR_MWH)


CONTRACTS: dict[str, pa.DataFrameSchema] = {
    "eia_ercot_hourly": pa.DataFrameSchema(
        {
            "period_utc": _hour_column(),
            "respondent": pa.Column(str, pa.Check.eq(config.EIA_RESPONDENT)),
            "type": pa.Column(str, pa.Check.isin(["D", "DF", "NG", "TI"])),
            # ERCOT's record is ~91,000 MWh; a missing value is allowed (dbt tracks missing hours).
            "value_mwh": _num(0, 150_000),
        },
        unique=["period_utc", "type"], strict=False, name="eia_ercot_hourly",
    ),
    "eia_ercot_zone_hourly": pa.DataFrameSchema(
        {
            "period_utc": _hour_column(),
            "parent": pa.Column(str, pa.Check.eq(config.EIA_RESPONDENT)),
            "zone_code": pa.Column(str, pa.Check.str_matches(r"^[A-Z]{2,6}$")),
            "demand_mwh": _num(0, 80_000),
        },
        unique=["period_utc", "zone_code"], strict=False, name="eia_ercot_zone_hourly",
    ),
    "eia_ercot_fuel_hourly": pa.DataFrameSchema(
        {
            "period_utc": _hour_column(),
            "respondent": pa.Column(str, pa.Check.eq(config.EIA_RESPONDENT)),
            "fuel_code": pa.Column(str, pa.Check.str_matches(r"^[A-Z]{2,4}$")),
            # Outer bound only; the per-fuel limits are in the table-level check below.
            "generation_mwh": _num(-STORAGE_LIMIT_MWH, 100_000),
        },
        checks=pa.Check(
            lambda df: df["generation_mwh"].isna() | (df["generation_mwh"] >= df["fuel_code"].map(_fuel_floor)),
            error="generation_mwh below the lowest allowed value for its fuel",
        ),
        unique=["period_utc", "fuel_code"], strict=False, name="eia_ercot_fuel_hourly",
    ),
    "weather_hourly": pa.DataFrameSchema(
        {
            "period_utc": _hour_column(),
            "city": pa.Column(str, pa.Check.isin(list(config.CITIES))),
            "temp_f": _num(-40, 130, nullable=False),
            "feels_like_f": _num(-70, 160),
            "humidity_pct": _num(0, 100),
        },
        unique=["period_utc", "city"], strict=False, name="weather_hourly",
    ),
    "weather_forecast_hourly": pa.DataFrameSchema(
        {
            "period_utc": _hour_column(),
            "city": pa.Column(str, pa.Check.isin(list(config.CITIES))),
            "forecast_temp_f": _num(-40, 130, nullable=False),
            "forecast_humidity_pct": _num(0, 100),
            "lead_hours": pa.Column(int, pa.Check.eq(24), coerce=True),
        },
        unique=["period_utc", "city"], strict=False, name="weather_forecast_hourly",
    ),
    "model_demand_forecast_hourly": pa.DataFrameSchema(
        {
            "period_utc": _hour_column(),
            "predicted_mwh": _num(10_000, 150_000, nullable=False),
            "predicted_fw_mwh": _num(10_000, 150_000),
            "model_version": pa.Column(str, pa.Check.str_matches(r"^hgb-v\d")),
        },
        unique=["period_utc"], strict=False, name="model_demand_forecast_hourly",
    ),
}


def validate(df: pd.DataFrame, dataset: str, quarantine_dir=None) -> pd.DataFrame:
    """Return the batch with types coerced, or quarantine it and raise ContractViolation."""
    schema = CONTRACTS.get(dataset)
    if schema is None or df.empty:
        return df
    df = df.reset_index(drop=True)
    try:
        return schema.validate(df, lazy=True)  # lazy: collect every failure, not just the first
    except SchemaErrors as err:
        cases = err.failure_cases
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = (quarantine_dir or config.DATA_DIR / "quarantine") / dataset / stamp
        out.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out / "rejected_batch.parquet", index=False)
        cases.to_csv(out / "failure_cases.csv", index=False)
        lines = []
        for (col, chk), grp in cases.groupby(["column", "check"], dropna=False, sort=False):
            examples = ", ".join(str(v) for v in grp["failure_case"].drop_duplicates().head(3))
            lines.append(f"  {col if col != schema.name else '(table)'} | {chk}: {len(grp)} rows, e.g. {examples}")
        lines = "\n".join(lines[:8])
        raise ContractViolation(
            f"{dataset}: batch of {len(df):,} rows broke its data contract and was NOT written.\n{lines}\n"
            f"Quarantined to {out}") from None


def audit_lake(raw_dir=None) -> int:
    """Check every file already in the lake against its contract. Read-only: nothing is moved or rewritten."""
    raw_dir = raw_dir or config.RAW_DIR
    problems = 0
    for dataset, schema in CONTRACTS.items():
        files = sorted((raw_dir / dataset).glob("*/*/data.parquet"))
        if not files:
            print(f"  -     {dataset:30} no files")
            continue
        bad = []
        for f in files:
            try:
                schema.validate(pd.read_parquet(f).reset_index(drop=True), lazy=True)
            except SchemaErrors as err:
                c = err.failure_cases
                bad.append(f"      {f.parent.parent.name}/{f.parent.name}: " + "; ".join(
                    f"{col} {chk} ({len(g)} rows, e.g. {g['failure_case'].iloc[0]})"
                    for (col, chk), g in c.groupby(["column", "check"], dropna=False, sort=False)))
        problems += len(bad)
        print(f"  {'ok' if not bad else 'FAIL':5} {dataset:30} {len(files)} files" + (f", {len(bad)} with problems" if bad else ""))
        if bad:
            print("\n".join(bad[:10]))
    return problems


if __name__ == "__main__":
    import sys
    print("Auditing the lake against the data contracts (read-only):")
    n = audit_lake()
    print("All files pass." if n == 0 else f"{n} file(s) would be rejected by today's contracts.")
    sys.exit(1 if n else 0)
