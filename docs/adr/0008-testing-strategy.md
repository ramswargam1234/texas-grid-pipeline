# ADR 0008: Testing strategy: unit, data and reconciliation tests with deliberate severities

- **Status:** Accepted
- **Date:** 2026-10-20

## Context

Real feeds have gaps and revisions. Tests that fail on every imperfection get ignored; tests that never fail
are useless. CI has no API keys, so it cannot use real data.

## Decision

| Layer | What it checks | Where |
|---|---|---|
| Python unit tests (pytest) | Parsing, pagination, retries + backoff, key redaction, S3 sync incl. state round trip (moto) | `tests/` |
| dbt unit tests | Model logic on hand-written rows: Uri gap math, `dim_date` seasons/weekends, multi-city zone averages | `transform/models/unit_tests.yml` |
| dbt data tests (51) | Keys unique/not null, accepted values, every star-schema foreign key, plausible ranges | `_*.yml`, `transform/tests/` |
| Reconciliation | 8 zones sum to ERCOT total within 3%; grid gaps; Uri window completeness | `transform/tests/` |
| CI | All of the above on a deterministic synthetic lake (`src/sample_data.py`) with no secrets | `ci.yml` |

Severity is chosen per test:
- **error** for anything that means the model is wrong (duplicate keys, broken relationships, bad values).
- **warn** for known source issues: missing EIA hours (error only above 240 hours) and the zone-vs-total
  mismatch.

## Consequences

- CI catches logic regressions in about a minute without touching real APIs.
- The zone reconciliation test found that EIA's zone and total datasets disagree by ~4–5% in parts of 2025
  (zones higher, no zones missing). That was documented as a known data issue rather than hidden or "fixed".
- **Trade-off:** warnings need a human to read them; they don't stop a run.
