"""The freshness gate fails only when a source is past its error threshold."""
import json

from src import freshness


def fake_results(tmp_path, statuses):
    results = [{"unique_id": f"source.texas_grid.raw.{name}", "status": status,
                "max_loaded_at": "2026-10-19T23:00:00+00:00", "max_loaded_at_time_ago_in_s": 3600 * 30,
                "criteria": {"warn_after": {"count": 2, "period": "day"}, "error_after": {"count": 4, "period": "day"}}}
               for name, status in statuses.items()]
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"metadata": {"generated_at": "2026-10-20T13:00:00Z"}, "results": results}))
    return path


def test_parses_dbt_results(tmp_path):
    rows = freshness.load(fake_results(tmp_path, {"eia_ercot_hourly": "pass"}))
    assert rows == [{"source": "eia_ercot_hourly", "status": "pass", "latest_data_utc": "2026-10-19T23:00:00+00:00",
                     "age_hours": 30.0, "warn_after": "2 days", "error_after": "4 days",
                     "checked_at_utc": "2026-10-20T13:00:00Z"}]


def test_gate_passes_on_warnings_and_fails_on_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(freshness, "RESULTS", fake_results(tmp_path, {"a": "pass", "b": "warn"}))
    assert freshness.gate() == 0
    monkeypatch.setattr(freshness, "RESULTS", fake_results(tmp_path, {"a": "pass", "b": "error"}))
    assert freshness.gate() == 1
    monkeypatch.setattr(freshness, "RESULTS", tmp_path / "missing.json")
    assert freshness.gate() == 2
