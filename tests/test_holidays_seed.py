"""The holiday calendar rules must match the real US calendar."""
from datetime import date

from src.holidays_seed import build, nth_weekday, observed


def test_rule_dates_match_real_calendar():
    assert nth_weekday(2024, 11, 3, 4) == date(2024, 11, 28)   # Thanksgiving 2024
    assert nth_weekday(2025, 5, 0, -1) == date(2025, 5, 26)    # Memorial Day 2025
    assert nth_weekday(2026, 9, 0, 1) == date(2026, 9, 7)      # Labor Day 2026
    assert nth_weekday(2025, 1, 0, 3) == date(2025, 1, 20)     # MLK Day 2025
    assert observed(date(2026, 7, 4)) == date(2026, 7, 3)      # Saturday -> Friday
    assert observed(date(2022, 12, 25)) == date(2022, 12, 26)  # Sunday -> Monday


def test_seed_is_one_row_per_date_and_federal_wins():
    rows = build(2020, 2030)
    dates = [r["holiday_date"] for r in rows]
    assert len(dates) == len(set(dates))
    by_date = {r["holiday_date"]: r for r in rows}
    # Christmas 2021 fell on Saturday, so Friday Dec 24 is the observed holiday, not just "Christmas Eve".
    assert by_date["2021-12-24"]["holiday_name"] == "Christmas Day"
    assert by_date["2021-12-24"]["holiday_type"] == "Federal (observed)"
    assert "2020-06-19" not in by_date and "2021-06-19" in by_date  # Juneteenth starts in 2021
    assert by_date["2024-11-28"]["is_nerc_holiday"] == "true"
