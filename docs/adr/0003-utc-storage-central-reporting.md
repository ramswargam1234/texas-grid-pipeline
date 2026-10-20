# ADR 0003: Store in UTC, report in US Central time

- **Status:** Accepted
- **Date:** 2026-10-19

## Context

EIA hourly data is published in UTC; Open-Meteo can return any time zone. Grid behavior (evening peaks,
weekdays) follows local Texas time, and Daylight Saving Time adds 23- and 25-hour days.

## Decision

All raw and staging timestamps are UTC (`period_utc`, `timestamptz`). Weather is requested in GMT so the two
sources join on the same key. Central time (`America/Chicago`) is derived only in marts and dimensions
(`period_local`, `date_local`, `date_key`, `hour_local`).

## Consequences

- Joins never break on DST transitions; there are no duplicated or missing join keys.
- Reports read naturally ("most common peak: 17:00 Central").
- **Trade-off:** local-day aggregates have 23 or 25 hours twice a year. Tests that count hours per day
  (for example the Uri load-shed window) are written against UTC-derived hour counts to stay exact.
