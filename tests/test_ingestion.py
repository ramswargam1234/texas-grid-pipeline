"""Unit tests with fake API responses (no network, no API key needed)."""
from datetime import date

import pandas as pd

from src.ingestion import config, eia_demand, weather
from src.ingestion.common import month_ranges, write_monthly


class FakeResp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class FakeSession:
    """Returns queued responses in order and records the params of each call."""

    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))
        return FakeResp(self.bodies.pop(0))


def eia_row(period, typ, value):
    return {"period": period, "respondent": "ERCO", "type": typ,
            "type-name": typ, "value": value, "value-units": "megawatthours"}


# ---------- helpers ----------

def test_month_ranges():
    assert month_ranges(date(2024, 1, 15), date(2024, 3, 2)) == [
        (date(2024, 1, 15), date(2024, 1, 31)),
        (date(2024, 2, 1), date(2024, 2, 29)),  # leap year
        (date(2024, 3, 1), date(2024, 3, 2)),
    ]


def test_write_monthly_is_idempotent(tmp_path):
    df = pd.DataFrame({"period_utc": pd.to_datetime(["2024-01-31T23:00", "2024-02-01T00:00"], utc=True),
                       "x": [1, 2]})
    paths = write_monthly(df, "demo", "period_utc", tmp_path)
    write_monthly(df, "demo", "period_utc", tmp_path)  # re-run
    assert len(paths) == 2
    assert all(len(pd.read_parquet(p)) == 1 for p in paths)  # overwritten, not duplicated


# ---------- EIA ----------

def test_eia_paginates_and_types(monkeypatch):
    monkeypatch.setattr(config, "EIA_API_KEY", "test-key")
    page1 = {"response": {"total": "3", "data": [eia_row("2024-07-01T20", "D", "75000"),
                                                  eia_row("2024-07-01T21", "D", "76500")]}}
    page2 = {"response": {"total": "3", "data": [eia_row("2024-07-01T22", "D", "77100")]}}
    session = FakeSession([page1, page2])

    df = eia_demand.fetch_range(date(2024, 7, 1), date(2024, 7, 1), session=session)

    assert len(df) == 3
    assert df["value_mwh"].dtype.kind == "f"  # strings converted to numbers
    assert df["period_utc"].dt.tz is not None  # timezone-aware UTC
    assert [c["offset"] for c in session.calls] == [0, 2]  # followed pagination
    assert session.calls[0]["facets[respondent][]"] == "ERCO"


def test_eia_dedupes():
    rows = [eia_row("2024-07-01T20", "D", "1"), eia_row("2024-07-01T20", "D", "1")]
    assert len(eia_demand.to_frame(rows)) == 1


# ---------- weather ----------

def test_weather_parse():
    body = {"hourly": {"time": ["2024-07-01T20:00", "2024-07-01T21:00"],
                       "temperature_2m": [101.2, 99.8],
                       "apparent_temperature": [108.0, 105.1],
                       "relative_humidity_2m": [35, 38]}}
    df = weather.fetch_city("dallas", 32.7, -96.8, date(2024, 7, 1), date(2024, 7, 1),
                            session=FakeSession([body]))
    assert list(df.columns[:3]) == ["period_utc", "city", "temp_f"]
    assert df["city"].unique().tolist() == ["dallas"]
    assert df["temp_f"].max() == 101.2


def test_weather_year_chunks():
    assert weather.year_chunks(date(2023, 6, 1), date(2024, 2, 1)) == [
        (date(2023, 6, 1), date(2023, 12, 31)),
        (date(2024, 1, 1), date(2024, 2, 1)),
    ]


# ---------- retries ----------

class StatusResp(FakeResp):
    def __init__(self, status, body=None, url="https://x/?api_key=SECRET123&a=1"):
        super().__init__(body or {})
        self.status_code = status
        self.url = url


def test_get_json_retries_then_succeeds():
    from src.ingestion.common import get_json
    session = FakeSession([])
    session.get = lambda *a, **k: responses.pop(0)
    responses = [StatusResp(504), StatusResp(503), StatusResp(200, {"ok": True})]
    waits = []
    assert get_json(session, "u", {}, 5, sleep=waits.append) == {"ok": True}
    assert waits == [2.0, 4.0]  # exponential backoff


def test_get_json_hides_api_key_on_client_error():
    import pytest
    from src.ingestion.common import get_json
    session = FakeSession([])
    session.get = lambda *a, **k: StatusResp(403)
    with pytest.raises(RuntimeError) as err:
        get_json(session, "u", {}, 5, sleep=lambda s: None)
    assert "SECRET123" not in str(err.value) and "api_key=***" in str(err.value)


# ---------- EIA zones ----------

def test_eia_zones_parse_and_paginate(monkeypatch):
    from src.ingestion import eia_zones
    monkeypatch.setattr(config, "EIA_API_KEY", "test-key")

    def zrow(period, code, value):
        return {"period": period, "subba": code, "subba-name": code + " zone", "parent": "ERCO",
                "parent-name": "ERCOT", "value": value, "value-units": "megawatthours"}

    page1 = {"response": {"total": "3", "data": [zrow("2024-07-01T20", "COAS", "21000"),
                                                  zrow("2024-07-01T20", "NCEN", "24000")]}}
    page2 = {"response": {"total": "3", "data": [zrow("2024-07-01T20", "FWES", "6000")]}}
    session = FakeSession([page1, page2])
    df = eia_zones.fetch_range(date(2024, 7, 1), date(2024, 7, 1), session=session)
    assert sorted(df["zone_code"]) == ["COAS", "FWES", "NCEN"]
    assert df["demand_mwh"].sum() == 51000.0
    assert session.calls[0]["facets[parent][]"] == "ERCO"
    assert [c["offset"] for c in session.calls] == [0, 2]


# ---------- EIA fuel mix ----------

def test_eia_fuel_parse_and_paginate(monkeypatch):
    from src.ingestion import eia_fuel
    monkeypatch.setattr(config, "EIA_API_KEY", "test-key")

    def frow(period, code, value):
        return {"period": period, "respondent": "ERCO", "respondent-name": "ERCOT", "fueltype": code,
                "type-name": code + " name", "value": value, "value-units": "megawatthours"}

    page1 = {"response": {"total": "3", "data": [frow("2024-07-01T20", "WND", "15000"),
                                                  frow("2024-07-01T20", "SUN", "18000")]}}
    page2 = {"response": {"total": "4", "data": [frow("2024-07-01T20", "BAT", "-500"),
                                                  frow("2024-07-01T20", "BAT", "-500")]}}  # duplicate
    session = FakeSession([page1, page2])
    df = eia_fuel.fetch_range(date(2024, 7, 1), date(2024, 7, 1), session=session)
    assert sorted(df["fuel_code"]) == ["BAT", "SUN", "WND"]
    assert df.loc[df.fuel_code == "BAT", "generation_mwh"].item() == -500.0  # charging stays negative
    assert session.calls[0]["facets[respondent][]"] == "ERCO"
    assert [c["offset"] for c in session.calls] == [0, 2]
