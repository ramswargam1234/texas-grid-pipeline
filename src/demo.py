"""One-command demo on synthetic data: no API keys, no AWS, no network.

Builds a synthetic data lake (Dec 2020 - Aug 2021, including a Winter Storm Uri-like freeze), runs the
full dbt build with every test, prints the headline report, and exports a dashboard snapshot. Everything
goes to data/demo/, so your real data and the committed dashboard snapshot are never touched.

Usage:
    python -m src.demo               # build and test everything
    python -m src.demo --dashboard   # ...then open the dashboard on the demo data
    make demo                        # same as the first line (also creates .venv if needed)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "data" / "demo"
STEPS = [
    ("Build synthetic data lake", ["-m", "src.sample_data"]),
    ("dbt build: models, snapshot, unit + data tests", ["-m", "src.run_dbt"]),
    ("Headline findings", ["-m", "src.report"]),
    ("Export dashboard snapshot", ["-m", "src.export_dashboard"]),
]


def demo_env() -> dict:
    env = dict(os.environ)
    env.update({
        "DATA_DIR": str(DEMO_DIR),
        "DASHBOARD_SNAPSHOT_DIR": str(DEMO_DIR / "snapshot"),
        "DBT_DUCKDB_PATH": str(DEMO_DIR / "warehouse.duckdb"),
        "DO_NOT_TRACK": "1",  # no dbt usage pings from the demo
        "PIPELINE_DEMO": "1",  # marks the snapshot so the dashboard shows a "synthetic data" banner
    })
    return env


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dashboard", action="store_true", help="open the Streamlit dashboard when done")
    a = ap.parse_args()

    shutil.rmtree(DEMO_DIR, ignore_errors=True)  # fresh run every time
    env, started = demo_env(), time.time()
    for i, (label, args) in enumerate(STEPS, 1):
        print(f"\n[{i}/{len(STEPS)}] {label}", flush=True)
        if subprocess.run([sys.executable, *args], cwd=ROOT, env=env).returncode != 0:
            raise SystemExit(f"Demo stopped: '{label}' failed.")
    print(f"\nDemo finished in {time.time() - started:.0f}s. Output in {DEMO_DIR.relative_to(ROOT)}/")

    if a.dashboard:
        try:
            import streamlit  # noqa: F401
        except ImportError:
            raise SystemExit("Streamlit isn't installed: pip install -r dashboard/requirements.txt")
        print("Opening the dashboard on demo data (Ctrl+C to stop)...")
        subprocess.run([sys.executable, "-m", "streamlit", "run", "dashboard/app.py"], cwd=ROOT, env=env)
    else:
        print("See it in the dashboard: python -m src.demo --dashboard")


if __name__ == "__main__":
    main()
