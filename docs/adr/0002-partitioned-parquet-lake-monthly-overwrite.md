# ADR 0002: Parquet lake with one file per month, overwritten on reload

- **Status:** Accepted
- **Date:** 2026-10-19

## Context

Source APIs (EIA, Open-Meteo) are slow and occasionally time out (EIA returned 504s during the first
backfill). EIA also revises recent data. Loads must be safe to re-run after any failure without creating
duplicates, and cheap to sync to S3.

## Decision

- Store raw data as Parquet at `raw/<dataset>/year=YYYY/month=MM/data.parquet` (Hive-style partitions).
- Always load **whole calendar months**, and **overwrite** that month's single file. A re-run replaces data
  instead of appending it, so loads are idempotent.
- Backfills **skip months that already exist** unless they are within the last 45 days (still being revised)
  or `--force` is passed. This makes an interrupted backfill resumable.
- HTTP calls retry with exponential backoff on timeouts, 429 and 5xx, and API keys are redacted from errors.
- Staging models de-duplicate on the natural key, keeping the latest `ingested_at`, as a second safety net.

## Alternatives considered

| Option | Why not |
|---|---|
| Append-only files per run | Duplicates on re-run; needs a separate dedupe/compaction step |
| One file per day | ~2,000 tiny files per dataset; slower S3 listing and reads |
| A database as the landing zone | Couples ingestion to a running server; harder to replay |

## Consequences

- Any load can be re-run safely, and the S3 sync uploads only files whose MD5 changed.
- **Trade-off:** the daily job rewrites the whole current month (a few hundred KB), not just new hours.
  Fine at this size; at much larger volumes, daily partitions or a table format (Iceberg/Delta) would be better.
