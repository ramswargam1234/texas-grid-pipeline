# ADR 0001: DuckDB + dbt as the warehouse

- **Status:** Accepted
- **Date:** 2026-10-19

## Context

The pipeline models about 600,000 hourly rows (grid, zones, weather) and grows by roughly 300 rows a day.
It needs SQL transformations with tests and documentation, has a budget of $0, and must run the same way on a
laptop, in Docker (Airflow) and on a throwaway GitHub Actions runner.

## Decision

Use **dbt** for all transformations and **DuckDB** (via `dbt-duckdb`) as the warehouse: a single file,
`data/warehouse.duckdb`. DuckDB reads the Parquet lake directly, either from local disk (`dev` target) or
from S3 (`cloud` target, using the `httpfs` extension).

## Alternatives considered

| Option | Why not (for now) |
|---|---|
| Snowflake / BigQuery | Real cost and account setup for a data set this small; adds credentials to every environment |
| Postgres | Needs a running server; slower for analytical scans; no native Parquet/S3 reads |
| pandas scripts only | No lineage, no declarative tests, no docs; harder to review |

## Consequences

- Zero infrastructure: the whole warehouse rebuilds from the lake in about one second.
- dbt gives lineage, 51 data tests, 3 unit tests and a snapshot, all warehouse-agnostic.
- **Trade-off:** DuckDB is single-writer and in-process. It is not a shared, multi-user warehouse. If several
  people or BI tools needed concurrent access, the same dbt project could target Snowflake or MotherDuck by
  adding a profile; most SQL would carry over, with small dialect fixes.
