"""The CI sample lake must cover what the dbt models need."""
from src.sample_data import build


def test_sample_lake_shapes():
    wx, grid, zones = build()
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
