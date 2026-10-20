"""Is every data source still delivering? Checks how old the newest hour of each source is.

Uses dbt's source freshness (thresholds per source in transform/models/staging/_sources.yml), in two steps so a
stale source never stops the dashboard from refreshing, but still fails the run so GitHub emails an alert:

    python -m src.freshness check   # run the check, save results (exit 0 even if a source is stale)
    python -m src.freshness gate    # at the end of the run: exit 1 if any source is past its error threshold
    python -m src.freshness show    # print the last results
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from src.ingestion import config

RESULTS = config.PROJECT_ROOT / "transform" / "target" / "sources.json"
ICONS = {"pass": "ok", "warn": "WARN", "error": "STALE", "runtime error": "FAILED"}


def load(path=None) -> list[dict]:
    """One row per source from dbt's sources.json: name, newest hour, age, status, thresholds."""
    path = path or RESULTS
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    rows = []
    for r in data.get("results", []):
        crit = r.get("criteria") or {}
        rows.append({
            "source": r["unique_id"].split(".")[-1],
            "status": r.get("status"),
            "latest_data_utc": r.get("max_loaded_at"),
            "age_hours": round(r["max_loaded_at_time_ago_in_s"] / 3600, 1) if r.get("max_loaded_at_time_ago_in_s") is not None else None,
            "warn_after": _fmt(crit.get("warn_after")),
            "error_after": _fmt(crit.get("error_after")),
            "checked_at_utc": data.get("metadata", {}).get("generated_at"),
        })
    return sorted(rows, key=lambda r: r["source"])


def _fmt(t: dict | None) -> str | None:
    return f"{t['count']} {t['period']}s" if t and t.get("count") else None


def stale(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["status"] in ("error", "runtime error")]


def show(rows: list[dict]) -> None:
    if not rows:
        print("No freshness results yet. Run: python -m src.freshness check")
        return
    for r in rows:
        age = f"{r['age_hours'] / 24:.1f} days" if r["age_hours"] is not None else "unknown"
        print(f"  {ICONS.get(r['status'], r['status']):6} {r['source']:30} newest hour {r['latest_data_utc']}  "
              f"({age} old; warn after {r['warn_after']}, error after {r['error_after']})")


def check() -> int:
    from src.run_dbt import run
    run("source freshness", stage="all")  # dbt returns failure on stale sources; the gate decides later
    rows = load()
    show(rows)
    if not rows:
        print("Freshness check produced no results (dbt could not run).", file=sys.stderr)
        return 2
    return 0


def gate() -> int:
    rows = load()
    if not rows:
        print("No freshness results to check.", file=sys.stderr)
        return 2
    bad = stale(rows)
    if bad:
        print(f"{len(bad)} source(s) stopped delivering data:", file=sys.stderr)
        show(bad)
        return 1
    print(f"All {len(rows)} sources are fresh ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC).")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["check", "gate", "show"])
    a = ap.parse_args()
    if a.action == "show":
        show(load())
        raise SystemExit(0)
    raise SystemExit(check() if a.action == "check" else gate())


if __name__ == "__main__":
    main()
