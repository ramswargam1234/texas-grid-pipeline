# ADR 0004: Airflow for local orchestration, GitHub Actions for the scheduled cloud run

- **Status:** Accepted
- **Date:** 2026-10-19

## Context

The pipeline needs a daily schedule, retries, and a manual backfill. Keeping a server running 24/7 costs
money; a laptop is often asleep.

## Decision

- **Airflow 3 (Docker Compose)** defines the DAGs `texas_grid_daily` and `texas_grid_backfill`, with retries,
  exponential backoff and `max_active_runs=1`. The S3 upload skips (exit 99) instead of failing when S3 is
  not configured; `dbt_build` uses `trigger_rule="none_failed"`.
- **GitHub Actions** runs the same steps every morning in the cloud (`daily-refresh.yml`) and runs CI on
  every push (`ci.yml`).
- Both call the **same CLI commands** (`python -m src...`), so behavior cannot drift between them.
- Pipeline code runs in its own virtualenv inside the Airflow image, isolating dbt's dependencies from
  Airflow's.

## Alternatives considered

| Option | Why not |
|---|---|
| Airflow on an always-on EC2 / managed Airflow | Monthly cost for a once-a-day job |
| Only GitHub Actions | Doesn't demonstrate DAG design, backfills, task-level retries |
| cron on the laptop | No retries, history or visibility; laptop sleeps |

## Consequences

- The production schedule costs $0 and needs no server.
- **Trade-off:** two schedulers describe the same flow. Keeping tasks as thin wrappers around CLI commands
  limits the duplication to the step order. In a team setting, one orchestrator would be chosen.
