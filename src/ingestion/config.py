"""Central config. Values come from environment variables (or a .env file)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"

# ---- EIA (U.S. Energy Information Administration) ----
EIA_API_KEY = os.getenv("EIA_API_KEY", "")
EIA_URL = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
EIA_RESPONDENT = "ERCO"  # ERCOT, the Texas grid
# D = demand, DF = day-ahead demand forecast, NG = net generation
EIA_TYPES = [t.strip() for t in os.getenv("EIA_TYPES", "D,DF,NG").split(",") if t.strip()]
EIA_PAGE_SIZE = 5000  # API maximum rows per request

# ---- Open-Meteo historical weather (no key needed) ----
WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_VARS = ["temperature_2m", "apparent_temperature", "relative_humidity_2m"]
CITIES = {
    "dallas": (32.7767, -96.7970),
    "houston": (29.7604, -95.3698),
    "austin": (30.2672, -97.7431),
    "san_antonio": (29.4241, -98.4936),
}

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "90"))
