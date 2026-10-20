# ADR 0010: Incremental hourly models with a 45-day lookback

- **Status:** Accepted
- **Date:** 2026-10-20

## Context

The hourly staging and fact tables (grid, weather, zones, fuel) were rebuilt from scratch on every run. With
5+ years of history, that re-reads every monthly Parquet file (from S3 in the cloud) to change the last few
days. Two kinds of data arrive late:

- **Revisions.** EIA republishes recent hours; the ingestion layer re-loads any month younger than 45 days.
- **Late joins.** The weather archive trails real time by ~6 days, so a grid hour is first loaded without its
  weather and only gets it on a later run.

## Decision

Make the seven big hourly models `incremental` (`delete+insert` on `period_utc`). On each run a model
re-processes hours from *latest loaded hour - 45 days* onward (`var('incremental_lookback_days')`), so revised
and late-joined hours are replaced, not appended. The shared macro `incremental_filter` computes that cutoff
first and inlines it as a constant, and on staging models also filters the lake's `year=/month=` partitions,
so DuckDB skips older files entirely (2 of 9 files read on the sample lake). Small dimensions and aggregates
stay full rebuilds: they are cheap and simpler to reason about.

## Alternatives considered

- **Append-only (`where period_utc > max(period_utc)`).** Fastest, but silently misses revisions and late
  weather, which is exactly the data this pipeline cares about.
- **`merge`.** Equivalent result here; `delete+insert` on whole hours is simpler and well supported by dbt-duckdb.
- **Keep full rebuilds.** Correct and simple, but cost grows with history and every run downloads the whole lake.

## Consequences

- `tests/test_incremental.py` (run in CI) builds a lake through July, adds August and revises late-July demand,
  runs incrementally, and asserts all seven tables are identical to a from-scratch build.
- A change to these models' logic or columns needs `python -m src.run_dbt --full-refresh` (`make full-refresh`).
- Revisions older than the lookback are not picked up incrementally; the ingestion layer doesn't re-load them
  either, and the SCD2 snapshot (ADR 0006) still records them. A monthly full refresh would close that gap.
- On a tiny dataset incremental runs are slightly slower (extra lookups); the saving grows with history.
