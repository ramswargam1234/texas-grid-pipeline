# ADR 0009: Estimating unserved demand during Winter Storm Uri

- **Status:** Accepted
- **Date:** 2026-10-19

## Context

During ERCOT's rolling blackouts (Feb 15 01:20 to Feb 18 00:42, 2021, Central), metered demand shows power
that was **delivered**, not power that was **needed**. A naive reading says demand fell on the coldest days.

## Decision

Estimate unserved energy in `fct_uri_unserved_hourly` two independent ways, over the 72 load-shed hours:

1. **Forecast gap (headline):** `max(day-ahead forecast − actual, 0)`.
2. **Weather model (upper bound):** one temperature slope plus a baseline per hour of day, fit on cold winter
   hours (Dec–Feb, below 50°F) from other winters, applied to Uri's temperatures. Hours colder than any
   training hour are flagged as extrapolated.

Validate against published figures before reporting.

## Consequences

- Result: **~1,342 GWh** unserved (forecast gap); ~1,895 GWh from the weather model.
- Validation: the forecast peaked at **76,783 MW** during load shed, matching ERCOT's own ~76.8 GW estimate
  of demand without blackouts. The weather model overshoots (85.4 GW), so it is reported as an upper bound.
- The largest hourly gap (28,885 MW) exceeds the 20 GW ERCOT ordered shed, which suggests delivered power also
  fell from local outages and industrial curtailment. That is a hypothesis, not something the data proves.
- **Limitation:** the day-ahead forecast is itself a model; the estimate is only as good as ERCOT's forecast
  for those days.
