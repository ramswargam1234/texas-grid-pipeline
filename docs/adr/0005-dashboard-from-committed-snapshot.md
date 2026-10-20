# ADR 0005: Public dashboard reads a committed CSV snapshot

- **Status:** Accepted
- **Date:** 2026-10-19

## Context

The dashboard is public (Streamlit Community Cloud). It should not hold AWS credentials or open the
warehouse, and it must load quickly.

## Decision

`src/export_dashboard.py` writes small aggregated CSVs plus `headline.json` to `dashboard/snapshot/`
(a few hundred KB). The daily GitHub Actions run commits them; Streamlit Cloud redeploys on that commit.
The app's cache is keyed on the snapshot file's modification time so new data always shows.

## Alternatives considered

| Option | Why not |
|---|---|
| Dashboard queries S3/DuckDB live | Public app would need credentials; slower cold starts |
| Hosted warehouse (MotherDuck) | Adds an account and a secret; possible later upgrade |

## Consequences

- No secrets in the public app; it loads in about a second.
- **Trade-offs:** data is at most a day old, and the repo gets one small bot commit per day, so you need
  `git pull` before working locally.
