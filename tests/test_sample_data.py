"""The CI sample lake must cover what the dbt models need."""
import pandas as pd
from src.sample_data import build


def test_sample_lake_shapes():
    wx, grid, zones, fuel, wx_fc = build()
    assert {"dallas", "houston", "austin", "san_antonio", "midland"} <= set(wx["city"])
    assert zones["zone_code"].nunique() == 8
    assert set(grid["type"]) == {"D", "DF", "NG"}
    # Covers a winter (for the Uri weather model) and a summer (for heat metrics).
    months = set(grid["period_utc"].dt.month)
    assert {12, 1, 2, 7} <= months
    # Simulated load shed: actual demand well below forecast during the storm.
    feb16 = grid[grid["period_utc"].dt.strftime("%Y-%m-%d") == "2021-02-16"]
    d = feb16[feb16["type"] == "D"]["value_mwh"].mean()
    f = feb16[feb16["type"] == "DF"]["value_mwh"].mean()
    assert f - d > 10_000
    # Fuel mix covers the main sources and adds up to net generation.
    assert {"NG", "WND", "SUN", "NUC", "COL"} <= set(fuel["fuel_code"])
    ng = grid[grid["type"] == "NG"]["value_mwh"].sum()
    assert abs(fuel["generation_mwh"].sum() - ng) / ng < 0.03
    # Day-ahead weather forecasts: same cities, from April 2021, errors of a few °F.
    assert set(wx_fc["city"]) == set(wx["city"])
    assert wx_fc["period_utc"].min() >= pd.Timestamp("2021-04-01", tz="UTC")
    m = wx_fc.merge(wx, on=["period_utc", "city"])
    assert 1 < (m["forecast_temp_f"] - m["temp_f"]).abs().mean() < 5
