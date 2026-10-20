"""The forecast must only use information available the day before, and never train on the month it predicts."""
import numpy as np
import pandas as pd

from src.forecast import demand_model as dm


def fake_hours(n_days=200):
    utc = pd.date_range("2024-01-01", periods=24 * n_days, freq="h", tz="UTC")
    local = utc.tz_convert("America/Chicago").tz_localize(None)
    temp = 60 + 25 * np.sin(np.arange(len(utc)) / (24 * 365) * 2 * np.pi)
    return pd.DataFrame({
        "period_utc": utc, "period_local": local, "demand_mwh": 40000 + 500 * temp,
        "avg_temp_f": temp, "avg_humidity_pct": 50.0, "hour_local": local.hour,
        "iso_day_of_week": local.dayofweek + 1, "is_business_day": local.dayofweek < 5,
        "is_holiday": False, "doy": local.dayofyear, "is_load_shed": False,
    })


def test_lags_use_only_past_demand():
    df = dm.make_features(fake_hours(10))
    row = df.iloc[200]
    assert row["demand_lag48"] == df.iloc[152]["demand_mwh"]
    assert row["demand_lag168"] == df.iloc[32]["demand_mwh"]
    assert df["demand_lag48"].iloc[:48].isna().all()  # nothing invented before the data starts


def test_backtest_trains_only_on_earlier_months(monkeypatch):
    df = dm.make_features(fake_hours())
    month = pd.Timestamp("2024-06-01")
    seen = {}

    class Spy:
        def fit(self, X, y):
            seen["n"] = len(X)
            return self

        def predict(self, X):
            return np.zeros(len(X))

    monkeypatch.setattr(dm, "new_model", Spy)
    preds = dm.backtest_month(df, month, "v1")
    assert seen["n"] == (df["month_start"] < month).sum()      # every earlier hour, nothing later
    dm.backtest_month(df, month, "v2")                          # v2 also drops hours with no level yet
    assert seen["n"] <= (df["month_start"] < month).sum()
    assert preds["trained_through"].iloc[0] < pd.Timestamp("2024-06-01", tz="UTC")
    assert len(preds) == (df["month_start"] == month).sum()


def test_load_shed_hours_are_not_training_data(monkeypatch):
    raw = fake_hours()
    raw.loc[100:171, "is_load_shed"] = True
    df = dm.make_features(raw)
    seen = {}
    monkeypatch.setattr(dm, "new_model", lambda: type("M", (), {
        "fit": lambda self, X, y: seen.setdefault("n", len(X)) and self,
        "predict": lambda self, X: np.zeros(len(X))})())
    dm.backtest_month(df, pd.Timestamp("2024-05-01"), "v1")
    assert seen["n"] == (df["month_start"] < pd.Timestamp("2024-05-01")).sum() - 72


def test_v2_level_uses_only_demand_from_2_days_back():
    df = dm.make_features(fake_hours(30))
    i = 24 * 25
    window = df["demand_mwh"].iloc[i - dm.LEVEL_GAP - dm.LEVEL_HOURS + 1: i - dm.LEVEL_GAP + 1]
    assert abs(df["level_mwh"].iloc[i] - window.mean()) < 1e-6
    assert df["level_mwh"].iloc[: dm.LEVEL_GAP + dm.LEVEL_HOURS // 2 - 1].isna().all()
