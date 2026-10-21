"""Bad API data must be stopped at the door: quarantined with a reason, never written to the lake."""
from datetime import datetime, timezone

import pandas as pd
import pytest

from src.ingestion import eia_demand, weather
from src.ingestion.common import write_monthly
from src.ingestion.contracts import ContractViolation, validate


def grid_batch(values=("75000", "76000"), types=("D", "D"), periods=("2024-07-01T20", "2024-07-01T21")):
    rows = [{"period": p, "respondent": "ERCO", "type": t, "type-name": t, "value": v,
             "value-units": "megawatthours"} for p, t, v in zip(periods, types, values)]
    return eia_demand.to_frame(rows)


def test_good_batch_passes_and_is_written(tmp_path):
    paths = write_monthly(grid_batch(), "eia_ercot_hourly", "period_utc", tmp_path / "raw")
    assert len(paths) == 1 and len(pd.read_parquet(paths[0])) == 2


def test_impossible_value_is_quarantined_not_written(tmp_path):
    bad = grid_batch(values=("75000", "7500000"))     # 7.5 million MWh in one hour: a units bug
    with pytest.raises(ContractViolation) as err:
        write_monthly(bad, "eia_ercot_hourly", "period_utc", tmp_path / "raw")
    assert "value_mwh" in str(err.value) and "in_range" in str(err.value)
    assert not (tmp_path / "raw").exists()                               # nothing reached the lake
    q = list((tmp_path / "quarantine" / "eia_ercot_hourly").glob("*/"))
    assert len(q) == 1 and (q[0] / "rejected_batch.parquet").exists() and (q[0] / "failure_cases.csv").exists()


def test_duplicate_keys_and_unknown_series_are_rejected(tmp_path):
    dupes = grid_batch(periods=("2024-07-01T20", "2024-07-01T20"))
    dupes = pd.concat([dupes.iloc[[0]], dupes.iloc[[0]]])                # to_frame dedupes, so force a duplicate
    with pytest.raises(ContractViolation):
        validate(dupes, "eia_ercot_hourly", tmp_path)
    with pytest.raises(ContractViolation, match="type"):
        validate(grid_batch(types=("D", "XX")), "eia_ercot_hourly", tmp_path)


def test_missing_column_and_future_hours_are_rejected(tmp_path):
    with pytest.raises(ContractViolation, match="value_mwh"):
        validate(grid_batch().drop(columns="value_mwh"), "eia_ercot_hourly", tmp_path)
    future = f"{datetime.now(timezone.utc).year + 1}-01-01T00"
    with pytest.raises(ContractViolation, match="future"):
        validate(grid_batch(periods=(future, "2024-07-01T21")), "eia_ercot_hourly", tmp_path)


def test_weather_in_celsius_by_mistake_is_caught(tmp_path):
    body = {"hourly": {"time": ["2024-07-01T20:00"], "temperature_2m": [38.0], "apparent_temperature": [41.0],
                       "relative_humidity_2m": [140]}}                       # humidity can't exceed 100%
    with pytest.raises(ContractViolation, match="humidity_pct"):
        validate(weather.to_frame(body, "dallas"), "weather_hourly", tmp_path)


def test_missing_value_is_allowed_and_extra_columns_are_fine(tmp_path):
    df = grid_batch(values=("75000", "")).assign(new_api_field="x")         # EIA gap + a field EIA added
    assert len(validate(df, "eia_ercot_hourly", tmp_path)) == 2


def fuel_batch(fuel_code, value):
    return pd.DataFrame({"period_utc": [pd.Timestamp("2026-07-22T15:00", tz="UTC")], "respondent": ["ERCO"],
                         "fuel_code": [fuel_code], "generation_mwh": [value]})


@pytest.mark.parametrize("code", ["BAT", "OES", "UES", "PS"])
def test_storage_fuels_may_charge_down_to_minus_30000(code, tmp_path):
    assert len(validate(fuel_batch(code, -11_553.0), "eia_ercot_fuel_hourly", tmp_path)) == 1   # real BAT value, 2026
    with pytest.raises(ContractViolation):
        validate(fuel_batch(code, -30_001.0), "eia_ercot_fuel_hourly", tmp_path)


def test_non_storage_fuels_keep_the_tight_negative_limit(tmp_path):
    assert len(validate(fuel_batch("SUN", -50.0), "eia_ercot_fuel_hourly", tmp_path)) == 1
    with pytest.raises(ContractViolation, match="lowest allowed"):
        validate(fuel_batch("NG", -11_553.0), "eia_ercot_fuel_hourly", tmp_path)
