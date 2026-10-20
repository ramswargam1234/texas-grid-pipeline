"""Central config. Values come from environment variables (or a .env file)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
# Where export_dashboard writes and the dashboard reads its CSV snapshot. The demo points this at
# data/demo/snapshot so it never overwrites the committed snapshot of real data.
SNAPSHOT_DIR = Path(os.getenv("DASHBOARD_SNAPSHOT_DIR", PROJECT_ROOT / "dashboard" / "snapshot"))

# ---- EIA (U.S. Energy Information Administration) ----
EIA_API_KEY = os.getenv("EIA_API_KEY", "")
EIA_URL = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
EIA_RESPONDENT = "ERCO"  # ERCOT, the Texas grid
# D = demand, DF = day-ahead demand forecast, NG = net generation
EIA_TYPES = [t.strip() for t in os.getenv("EIA_TYPES", "D,DF,NG").split(",") if t.strip()]
EIA_PAGE_SIZE = 5000  # API maximum rows per request
# Hourly demand for each ERCOT weather zone ("sub-balancing authority"), parent = ERCO.
EIA_ZONE_URL = "https://api.eia.gov/v2/electricity/rto/region-sub-ba-data/data/"
# Hourly net generation by fuel type (wind, solar, gas, coal, nuclear, ...).
EIA_FUEL_URL = "https://api.eia.gov/v2/electricity/rto/fuel-type-data/data/"

# ---- Open-Meteo historical weather (no key needed) ----
WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_VARS = ["temperature_2m", "apparent_temperature", "relative_humidity_2m"]

# ---- Open-Meteo Previous Runs API: what the weather FORECAST said, archived (no key needed) ----
# `<var>_previous_day1` = the value forecast 24 hours before each hour, i.e. a day-ahead weather forecast.
# GFS is used throughout because its archive reaches back to March 2021 (most models start in 2024).
WEATHER_FORECAST_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
WEATHER_FORECAST_MODEL = os.getenv("WEATHER_FORECAST_MODEL", "gfs_seamless")
WEATHER_FORECAST_START = "2021-04-01"
CITIES = {
    # The 4 metros behind the statewide "average Texas temperature" (see METRO_CITIES).
    "dallas": (32.7767, -96.7970),
    "houston": (29.7604, -95.3698),
    "austin": (30.2672, -97.7431),
    "san_antonio": (29.4241, -98.4936),
    # One reference city for each remaining ERCOT weather zone.
    "midland": (31.9973, -102.0779),        # Far West (Permian Basin)
    "abilene": (32.4487, -99.7331),         # West
    "wichita_falls": (33.9137, -98.4934),   # North
    "tyler": (32.3513, -95.3011),           # East
    "corpus_christi": (27.8006, -97.3964),  # Southern
}
METRO_CITIES = ["dallas", "houston", "austin", "san_antonio"]

# ---- AWS S3 (Phase 2) ----
# Credentials come from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY in .env (read by boto3 and dbt).
S3_BUCKET = os.getenv("S3_BUCKET", "")
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "90"))
