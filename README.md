# Texas Grid & Weather Data Pipeline

[![CI](https://github.com/ramswargam1234/texas-grid-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/ramswargam1234/texas-grid-pipeline/actions/workflows/ci.yml)
[![Daily refresh](https://github.com/ramswargam1234/texas-grid-pipeline/actions/workflows/daily-refresh.yml/badge.svg)](https://github.com/ramswargam1234/texas-grid-pipeline/actions/workflows/daily-refresh.yml)

**Live dashboard:** https://texas-grid-ram.streamlit.app

An end-to-end data pipeline that joins **hourly Texas power grid (ERCOT) demand** with **hourly weather for 9 Texas cities** to answer:

- How much does temperature drive Texas electricity demand?
- When is the grid under the most stress, and how good is the day-ahead forecast?
- What happened to demand during extreme weather events (e.g., heat waves, the Feb 2021 freeze)?
- Which of ERCOT's 8 weather zones are most sensitive to heat?

## Architecture (target)

```
EIA API (ERCOT hourly) ──┐
                         ├─► Python ingestion ─► Raw Parquet (S3 / local) ─► dbt models ─► Dashboard
Open-Meteo (weather) ────┘   idempotent,         partitioned year/month        staging → marts
                             paginated
                └───────────────── orchestrated by Airflow (daily) ─────────────────┘
```

## Roadmap

- [x] **Phase 1: Ingestion.** EIA + Open-Meteo loaders, pagination, monthly idempotent writes, unit tests
- [x] **Phase 2: Storage.** Incremental sync of the Parquet lake to S3 (least-privilege IAM user); dbt can build straight from S3
- [x] **Phase 3: Transform.** dbt + DuckDB: staging, hourly fact table, weather-demand marts, data tests
- [x] **Phase 4: Orchestrate.** Airflow 3 DAGs (daily incremental + manual backfill) in Docker Compose, with retries and an isolated pipeline virtualenv
- [x] **Phase 5: Serve.** Streamlit dashboard (demand vs. temperature, peak hours, Winter Storm Uri, forecast error), refreshed by Airflow

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add your free EIA key
python -m pytest -q             # run tests
python -m src.sample_data       # optional: synthetic data lake, no API keys needed

# Backfill (safe to re-run: retries on server errors, skips months already loaded)
python -m src.ingestion.eia_demand --start 2021-01-01
python -m src.ingestion.eia_zones  --start 2021-01-01
python -m src.ingestion.weather    --start 2021-01-01

# Daily refresh
python -m src.ingestion.eia_demand --days 7
python -m src.ingestion.eia_zones  --days 7
python -m src.ingestion.weather    --days 14

# Upload new/changed files to S3
python -m src.storage.s3_sync

# Transform + test (builds data/warehouse.duckdb)
python -m src.run_dbt                  # from the local lake
python -m src.run_dbt --target cloud   # straight from S3

# Headline findings
python -m src.report
```

## Dashboard

Streamlit app in [`dashboard/app.py`](dashboard/app.py). It reads small CSV snapshots exported
from the warehouse (`dashboard/snapshot/`), so the hosted version needs no database or credentials.

```bash
python -m src.export_dashboard                 # refresh snapshot (Airflow does this daily)
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py                 # http://localhost:8501
```

## Orchestration (Airflow)

```bash
docker compose up -d --build     # first build takes a few minutes
open http://localhost:8080       # Airflow UI
docker compose down              # stop
```

| DAG | Schedule | Tasks |
|---|---|---|
| `texas_grid_daily` | 7:00 AM Central | `ingest_grid` + `ingest_zones` + `ingest_weather` → `upload_to_s3` → `dbt_build` → `report` + `export_dashboard` |
| `texas_grid_backfill` | manual (param: `start`) | backfill both sources → `upload_to_s3` → `dbt_build` |

- Retries with exponential backoff on every task; one run at a time (`max_active_runs=1`).
- `upload_to_s3` **skips** (doesn't fail) when `S3_BUCKET` isn't set; `dbt_build` uses `trigger_rule="none_failed"` so it still runs.
- Pipeline code runs in its own virtualenv inside the image, so dbt and Airflow dependencies never conflict.
- Tasks call the same CLI commands as the Quickstart, so local and scheduled runs behave identically.

## Automation (GitHub Actions)

| Workflow | Trigger | What it does |
|---|---|---|
| [`ci.yml`](.github/workflows/ci.yml) | every push and pull request | Unit tests, then a full `dbt build` (models + data tests) on a synthetic data lake from `src/sample_data.py`. No secrets needed. |
| [`daily-refresh.yml`](.github/workflows/daily-refresh.yml) | daily 13:17 UTC, or on demand | Pulls the lake from S3, loads the latest EIA and weather data, syncs back to S3, rebuilds dbt, and commits a fresh dashboard snapshot. Streamlit Cloud redeploys on that commit. |

The daily job uses its own IAM access key (stored as GitHub secrets `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, plus `EIA_API_KEY`), separate from the local development key, so either can be revoked on its own.

## AWS infrastructure (Terraform)

All AWS resources are defined in [`infra/terraform`](infra/terraform). They were first created by hand in the
console, then adopted into Terraform with `import` blocks, so nothing was recreated.

| Resource | Hardening |
|---|---|
| S3 bucket (`raw/` lake) | Public access fully blocked; ACLs disabled; SSE-S3 encryption; **HTTPS-only bucket policy**; `prevent_destroy` |
| Versioning + lifecycle | Overwritten files kept **30 days** for rollback, then expired; stale multipart uploads cleaned up |
| Pipeline IAM user + policy | Least privilege: list/read/write **only under `raw/`** in this one bucket; no delete; no console login |
| Access keys | Separate keys for laptop and GitHub Actions; never in Terraform state, never in git |

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # add your AWS account ID
terraform init
terraform plan      # review: imports + additions, 0 to destroy
terraform apply
```

Other safeguards: CI runs with a read-only `GITHUB_TOKEN`; Dependabot opens weekly PRs for Python packages and
GitHub Actions; MFA on the root account and a zero-spend budget alert.

## dbt models

```
raw parquet ─► stg_eia__ercot_hourly ─► int_grid__hourly_pivoted ─┬─► fct_grid_hourly ─┬─► agg_grid_daily
           └─► stg_weather__hourly ──► int_weather__texas_hourly ─┘                   └─► agg_demand_by_temperature
                                       int_grid__hourly_pivoted ─────► dq_grid_missing_hours
```

| Model | Grain | What it answers |
|---|---|---|
| `fct_grid_hourly` | 1 row / hour | Demand, forecast, generation + Texas weather, UTC and Central time |
| `agg_grid_daily` | 1 row / day | Daily peak demand, peak hour, weather, forecast accuracy |
| `agg_demand_by_temperature` | 1 row / 5°F band | How demand rises with heat and cold |
| `dq_grid_missing_hours` | 1 row / missing hour | Gaps in the EIA feed |
| `fct_uri_unserved_hourly` | 1 row / hour, Feb 8–21 2021 | Forecast, weather-model and actual demand during Winter Storm Uri |
| `agg_uri_summary` | 1 row | Estimated unserved energy (GWh) during the blackouts |
| `fct_zone_hourly` | 1 row / hour / zone | Demand in each of ERCOT's 8 weather zones, joined to that zone's own weather |
| `agg_zone_profile` | 1 row / zone | Share of energy, peak, and heat sensitivity (MWh and % per °F above 75°F) |

**Data tests (33):** primary keys unique/not null, accepted series types and cities, one row per hour and type/city, plausible demand and temperature ranges, weather coverage, and a gap-tolerance test that **warns on any missing hour and fails above 240**, a completeness check on the 72 Uri load-shed hours, zone codes that must match the zone seed, and a check that the 8 weather zones add up to ERCOT's total within 3%.

## Finding: demand that went unserved during Winter Storm Uri

ERCOT ordered rolling blackouts from **1:20 AM Feb 15 to 12:42 AM Feb 18, 2021**. During those hours the EIA data records
the power that was *delivered*, not the power people *needed*, so a naive reading says demand fell during the coldest
days on record. `fct_uri_unserved_hourly` estimates the missing demand two independent ways:

1. **Forecast gap:** ERCOT's day-ahead demand forecast minus actual demand.
2. **Weather model:** one temperature slope plus a baseline for each hour of day, fit on cold winter hours (Dec–Feb, below 50°F)
   from every other winter, then applied to Uri's temperatures. Hours colder than any training hour are flagged as extrapolated.

**Result:** an estimated **~1,340 GWh** of demand went unserved over the 72 load-shed hours (forecast gap; the weather model gives ~1,900 GWh as an upper bound). The forecast peaked at **76,783 MW** during load shed, matching ERCOT's own ~76.8 GW estimate. The largest hourly gap, **28,885 MW**, exceeds the 20 GW ERCOT ordered shed, suggesting delivered power also fell from local outages and industrial cutbacks. For reference, ERCOT reported shedding up to 20 GW and estimated peak demand
of about 76.8 GW without load shed ([S&P Global](https://www.spglobal.com/commodity-insights/en/news-research/latest-news/electric-power/022421-ercot-lost-almost-half-of-generation-capacity-in-storm-causing-20-gw-load-shed)).

## Known data issue: zone totals in 2025

`assert_zones_sum_to_ercot_total` checks every hour that ERCOT's 8 weather zones add up to its total demand.
2021–2023 reconcile almost perfectly. In 2025, the zones sum to roughly **4–5% more** than the total in about
7–20% of hours each month (never less), with no missing zones. This is a difference between EIA's two published
datasets, not a pipeline error, so the test warns rather than fails. Zone heat-sensitivity is measured against
each zone's own history and isn't affected. The newest hours sometimes lack a zone until EIA finishes publishing.

## Data layout

```
data/raw/
  eia_ercot_hourly/year=YYYY/month=MM/data.parquet       # demand (D), forecast (DF), net generation (NG), MWh
  eia_ercot_zone_hourly/year=YYYY/month=MM/data.parquet  # demand per ERCOT weather zone, MWh
  weather_hourly/year=YYYY/month=MM/data.parquet     # temp_f, feels_like_f, humidity_pct per city
```

All timestamps are **UTC** so the two sources join cleanly on `period_utc`. Each month is a single file that's overwritten on re-run, so backfills never create duplicates.

## Data sources

- [U.S. Energy Information Administration (EIA) Open Data](https://www.eia.gov/opendata/), hourly electric grid monitor (ERCOT)
- [Open-Meteo Historical Weather API](https://open-meteo.com/) (non-commercial use)
