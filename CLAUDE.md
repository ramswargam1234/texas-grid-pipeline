# CLAUDE.md: Texas Grid & Weather Data Pipeline

Context for Claude Code. Read this first in every session.

## Who and why
- Owner: Ram Swargam, MS Data Engineering student at SMU (Dallas), graduating May 2027. Targeting Data Engineer
  new-grad roles (AT&T TDP, Texas Instruments, Goldman Sachs, IBM). This is his main resume project.
- It is a **data pipeline** (data engineering project), not a consumer app. Final goal on the roadmap: a small
  "Texas Grid Stress" app on top of the pipeline (zone-level next-day grid stress + plain advice). Keep it simple:
  no logins, payments or mobile app.
- Ram prefers direct, execution-first help, short simple explanations, and clear recommendations (one option, not five).
  Explain what you changed in plain words; he is learning.

## What the pipeline does
Hourly ERCOT (Texas grid) demand, zones and fuel mix from the EIA API + hourly weather (observed and day-ahead
forecasts) for 9 Texas cities from Open-Meteo -> partitioned Parquet lake (local `data/raw/` and S3) -> dbt + DuckDB
warehouse with a star schema and 100+ tests -> Streamlit dashboard. Orchestrated daily by GitHub Actions (cloud)
and Airflow 3 in Docker (local). Infra: AWS S3 + IAM via Terraform.

- Repo: github.com/ramswargam1234/texas-grid-pipeline (public). Live dashboard: texas-grid-ram.streamlit.app
- Roadmap with ticks (owner-maintained): a private claude.ai artifact "Texas Grid Pipeline Roadmap".

## Layout
- `src/ingestion/`: loaders `eia_demand.py`, `eia_zones.py`, `eia_fuel.py`, `weather.py`, `weather_forecast.py`
  (Open-Meteo Previous Runs API, GFS, 24 h lead); `common.py` (`get_json` retries/backoff + key redaction,
  `write_monthly` = one file per UTC month, overwrite = idempotent); `contracts.py` (Pandera data contracts, enforced
  inside `write_monthly`, bad batches go to `data/quarantine/`); `config.py` (all settings from env / `.env`).
- `src/storage/s3_sync.py`: MD5-vs-ETag sync of the lake; `--download`, `--state-download/--state-upload`
  (`state/warehouse.duckdb` keeps dbt snapshot history between cloud runs).
- `src/forecast/demand_model.py`: HistGradientBoosting demand model, walk-forward monthly backtest, v1/v2
  (`--model`), predicts each hour with observed AND forecast weather. Writes `model_demand_forecast_hourly` to the lake.
- `src/run_dbt.py` (stages: `main` excludes tag:forecast, `forecast` = only it; `--full-refresh`),
  `src/freshness.py` (check / gate / show), `src/report.py`, `src/export_dashboard.py` (CSV snapshot for the
  dashboard), `src/demo.py` (`make demo`, synthetic data, writes only to `data/demo/`), `src/sample_data.py`,
  `src/holidays_seed.py`.
- `transform/` (dbt): staging, intermediate (views), dims, marts, `forecast/` (tag forecast, second stage), seeds
  (zones, series, fuel types, US holidays), snapshot `snp_eia_daily_totals`, unit tests in `models/unit_tests.yml`,
  macros `zone_heat.sql`, `incremental_filter.sql` (45-day lookback, partition pruning).
- `dashboard/app.py` (Streamlit, reads `dashboard/snapshot/*.csv`, `DASHBOARD_SNAPSHOT_DIR` overrides).
- `orchestration/` Airflow DAGs `texas_grid_daily`, `texas_grid_backfill`; `docker-compose.yml`.
- `.github/workflows/`: `ci.yml` (pytest with RUN_SLOW_TESTS=1 + `python -m src.demo`), `daily-refresh.yml`
  (13:17 UTC: S3 down, ingest, S3 up, dbt, forecast, dbt forecast stage, freshness, report, export, commit snapshot,
  freshness gate). `infra/terraform/`, `docs/adr/` (ADRs 0001-0010), `docs/architecture.svg`, `Makefile`.

## Commands
```bash
source .venv/bin/activate
python -m pytest -q                     # fast tests; RUN_SLOW_TESTS=1 adds the incremental equivalence test
make demo                               # whole pipeline on synthetic data, no keys
python -m src.run_dbt                   # stage 1 (incremental hourly models)
python -m src.forecast                  # model backtest (new/recent months only)
python -m src.run_dbt --stage forecast  # stage 2
python -m src.report                    # headline findings
python -m src.freshness check           # source freshness
python -m src.ingestion.contracts       # read-only audit of the lake vs contracts
python -m src.storage.s3_sync           # push lake to S3
make help                               # all shortcuts
```

## Rules (important)
- **Secrets:** never read, print or commit `.env`, `~/.aws/credentials`, `terraform.tfvars`, tfstate or tfplan.
  Never put keys in code, logs or chat. You never need the values.
- **Git order:** run tests -> `git add -A` -> `git commit` -> `git pull --rebase` -> `git push`. The daily bot commits
  `dashboard/snapshot/`, so always pull before pushing. Check `git status` first: `data/`, `.env`, `.venv/` must never
  be staged. Never commit `dashboard/snapshot/` by hand (the workflow owns it); don't run `export_dashboard` and commit.
- **Ask before:** `git push`, anything that changes AWS/Terraform, deleting data, `--force` backfills, changing
  GitHub workflows' secrets.
- **After changing logic of an incremental model:** `python -m src.run_dbt --full-refresh` once.
- **After changing the forecast model:** bump the version in `MODELS` so every month is re-backtested.
- Keep every change tested: add pytest/dbt tests, run `make demo` (it is what CI runs), keep the README, ADRs and
  the dashboard's test counts in sync. Prefer small, honest claims; label caveats (e.g. synthetic vs real results).
- EIA/Open-Meteo may be unreachable from some environments; use `src/sample_data.py` / `make demo` to test.

## Known data facts (real data)
- Coverage 2021-01 to now, ~50,000 hours, 600K+ rows. All-time peak 91,075 MWh (2026-07-22 18:00 CT).
- Heat sensitivity +1,389 MWh/°F above 75°F; hot vs mild 1.76x. ERCOT day-ahead forecast 2.47% MAPE.
- Winter Storm Uri: ~1,342 GWh unserved (forecast gap), validated vs ERCOT's ~76.8 GW estimate.
- Zones: Southern +3.71%/°F most heat-sensitive, Far West +0.24%/°F least. 6 of 8 zones changed 2021-2026 beyond
  95% CIs, all robust to the known EIA issue (zone totals ~4-5% above ERCOT total in parts of 2025, ADR 0008).
- Fuel mix: renewables 28% (2021) -> 37% (2025), coal 19% -> 13%; gas 42% of all hours, 49% at peak, 66% during Uri.
- Holidays: New Year's Eve -11.3%, day after Thanksgiving -10.0%, Christmas -8.8% vs nearby same weekdays.
- Forecast v2: 4.36% MAPE vs ERCOT 2.38% (48,539 h); 2025 alone 3.65% vs 2.46%. With GFS day-ahead weather 4.70%:
  weather forecast adds only +0.34 pts (GFS 4-city temp error 2.0°F); most of the gap is the model.
- `assert_weather_forecast_plausible` warns on 6 hours: real cold fronts/storms (e.g. Abilene, Jan 1 2022). Expected.

## Status and next steps (as of 2026-10-21)
Done: Phase 1-5, Tier 1, t2a fuel mix, t2q zone heat trend (+ robustness), t2b architecture diagram, t2c `make demo`,
t2d holidays, t2e forecast, t2r weather vs model error split, t2f freshness, t2g incremental models.

In progress: **t2h data contracts**: code is in the repo; before relying on it, run `python -m src.ingestion.contracts`
on the real lake. If any dataset FAILs, adjust the contract (real EIA data can have odd values) rather than letting the
daily run stop. Then commit and push.

Next, in order:
1. Keep-awake GitHub Action for the Streamlit app (it sleeps after inactivity; recruiters would see a sleep page).
   Headless browser visits the URL every few hours and clicks the wake button if shown. No secrets needed.
2. Tier 2 remaining: t2i run log table on the dashboard, t2j Airflow 3 asset-based scheduling, t2k code quality
   (ruff, mypy, sqlfluff, pre-commit), t2l dbt docs site on GitHub Pages, t2m FastAPI service for the marts,
   t2n anomaly detection on daily demand, t2o email alerts near record demand / on failures, t2p S3 storage-class rule.
3. Tier 3 (optional): GitHub OIDC for AWS, Texas zone map, MotherDuck, real-time ERCOT prices + demand with Kafka
   (Redpanda), SPP/MISO comparison, Snowflake target, Iceberg + Athena, DuckDB vs Polars vs PySpark benchmark,
   dev/prod environments, recorded API tests.
4. Final goal: Texas Grid Stress app (stress score per zone, city picker page, plain advice, email alert sign-up, launch).
5. Launch: fix LinkedIn link on GitHub profile (linkedin.com/in/ramswargam), pin the repo, resume bullets, Uri write-up,
   LinkedIn post, 2-minute demo video, interview stories.
Not planned: CDC (Debezium), which needs an operational database.
