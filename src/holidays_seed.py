"""Generate the US holiday calendar seed used by dbt (transform/seeds/us_holidays.csv).

Rules, not a lookup service, so the calendar is reproducible and needs no extra dependency.
Covers US federal holidays (with the weekday they are observed on), plus the days around them
when Texas demand also drops (day after Thanksgiving, Christmas Eve, New Year's Eve).
`is_nerc_holiday` marks the six holidays the grid industry itself treats as off-peak days.

Usage:
    python -m src.holidays_seed              # writes 2020-2030
    python -m src.holidays_seed --end 2035
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "transform" / "seeds" / "us_holidays.csv"
NERC = {"New Year's Day", "Memorial Day", "Independence Day", "Labor Day", "Thanksgiving Day", "Christmas Day"}


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th given weekday (Mon=0) of a month; n=-1 means the last one."""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def observed(d: date) -> date:
    """Federal rule: Saturday holidays are observed Friday, Sunday holidays on Monday."""
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


def holidays(year: int) -> list[tuple[date, str, str]]:
    fixed = [(date(year, 1, 1), "New Year's Day"), (date(year, 7, 4), "Independence Day"),
             (date(year, 11, 11), "Veterans Day"), (date(year, 12, 25), "Christmas Day")]
    if year >= 2021:  # Juneteenth became a federal holiday in June 2021
        fixed.append((date(year, 6, 19), "Juneteenth"))
    floating = [(nth_weekday(year, 1, 0, 3), "Martin Luther King Jr. Day"),
                (nth_weekday(year, 2, 0, 3), "Presidents' Day"),
                (nth_weekday(year, 5, 0, -1), "Memorial Day"),
                (nth_weekday(year, 9, 0, 1), "Labor Day"),
                (nth_weekday(year, 10, 0, 2), "Columbus Day"),
                (nth_weekday(year, 11, 3, 4), "Thanksgiving Day")]
    rows = [(d, name, "Federal") for d, name in fixed + floating]
    rows += [(observed(d), name, "Federal (observed)") for d, name in fixed if observed(d) != d]
    thanksgiving = floating[-1][0]
    rows += [(thanksgiving + timedelta(days=1), "Day after Thanksgiving", "Holiday-adjacent"),
             (date(year, 12, 24), "Christmas Eve", "Holiday-adjacent"),
             (date(year, 12, 31), "New Year's Eve", "Holiday-adjacent")]
    return rows


def build(start: int = 2020, end: int = 2030) -> list[dict]:
    # One row per date. If two land on the same day (e.g. Christmas observed on Dec 24),
    # the federal holiday wins over a holiday-adjacent day.
    rank = {"Federal": 0, "Federal (observed)": 1, "Holiday-adjacent": 2}
    best: dict[date, tuple[date, str, str]] = {}
    for year in range(start, end + 1):
        for row in holidays(year):
            if not start <= row[0].year <= end:
                continue  # e.g. New Year's Day 2020 observed on Dec 31, 2019 falls outside the range
            if row[0] not in best or rank[row[2]] < rank[best[row[0]][2]]:
                best[row[0]] = row
    return [{"holiday_date": d.isoformat(), "holiday_name": name, "holiday_type": kind,
             "is_nerc_holiday": str(name in NERC and kind != "Holiday-adjacent").lower()}
            for d, name, kind in sorted(best.values())]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2020)
    ap.add_argument("--end", type=int, default=2030)
    a = ap.parse_args()
    rows = build(a.start, a.end)
    with SEED.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} holidays ({a.start}-{a.end}) to {SEED}")


if __name__ == "__main__":
    main()
