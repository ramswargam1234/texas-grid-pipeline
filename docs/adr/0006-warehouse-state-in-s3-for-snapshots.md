# ADR 0006: Keep the warehouse file in S3 so dbt snapshots persist

- **Status:** Accepted
- **Date:** 2026-10-20

## Context

`snp_eia_daily_totals` is a type-2 dbt snapshot that records when EIA revises a day's published totals.
Snapshots only work if the previous history still exists at the next run. GitHub Actions runners start
empty every time, so a freshly built DuckDB file would lose all history.

## Decision

The daily job downloads `s3://<bucket>/state/warehouse.duckdb` before `dbt build` and uploads it after a
successful build. The IAM policy grants the pipeline user `state/*` in addition to `raw/*`. Bucket
versioning (30-day retention) keeps earlier copies of the file.

## Alternatives considered

| Option | Why not |
|---|---|
| Write the snapshot table out as Parquet in the lake | More custom code; dbt snapshots expect a persistent table |
| Hosted warehouse (MotherDuck/Snowflake) | Cost and another secret; the right choice at larger scale |

## Consequences

- Revision history accumulates across cloud runs, and only S3 is needed.
- **Trade-off: last writer wins.** If the laptop and the cloud job both upload the warehouse, one copy
  overwrites the other. Mitigations: the workflow has a concurrency group, the laptop only uploads state
  deliberately, and S3 versioning allows restoring an earlier file. A hosted warehouse would remove this risk.
