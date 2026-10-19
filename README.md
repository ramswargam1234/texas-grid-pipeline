# Texas Grid & Weather Data Pipeline

An end-to-end data pipeline that joins **hourly Texas power grid (ERCOT) demand** with **hourly weather for Dallas, Houston, Austin and San Antonio** to answer:

- How much does temperature drive Texas electricity demand?
- When is the grid under the most stress, and how good is the day-ahead forecast?
- What happened to demand during extreme weather events (e.g., heat waves, the Feb 2021 freeze)?

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
- [ ] **Phase 2: Storage.** Raw Parquet to S3
- [ ] **Phase 3: Transform.** dbt + DuckDB: staging, hourly fact table, weather-demand marts, data tests
- [ ] **Phase 4: Orchestrate.** Airflow DAG (daily incremental + backfill) in Docker Compose
- [ ] **Phase 5: Serve.** Dashboard: demand vs. temperature, peak hours, forecast error

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add your free EIA key
python -m pytest -q             # run tests

# Backfill (safe to re-run: retries on server errors, skips months already loaded)
python -m src.ingestion.eia_demand --start 2021-01-01
python -m src.ingestion.weather    --start 2021-01-01

# Daily refresh
python -m src.ingestion.eia_demand --days 7
python -m src.ingestion.weather    --days 14
```

## Data layout

```
data/raw/
  eia_ercot_hourly/year=YYYY/month=MM/data.parquet   # demand (D), forecast (DF), net generation (NG), MWh
  weather_hourly/year=YYYY/month=MM/data.parquet     # temp_f, feels_like_f, humidity_pct per city
```

All timestamps are **UTC** so the two sources join cleanly on `period_utc`. Each month is a single file that's overwritten on re-run, so backfills never create duplicates.

## Data sources

- [U.S. Energy Information Administration (EIA) Open Data](https://www.eia.gov/opendata/), hourly electric grid monitor (ERCOT)
- [Open-Meteo Historical Weather API](https://open-meteo.com/) (non-commercial use)
