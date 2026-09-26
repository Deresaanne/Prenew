"""
workflow.py

CLI script that:
1. Loads backend/data/influencers.csv
2. Computes insights via backend/insights_engine.py: the top N influencers
   ranked by a score, either overall, within groups (by primary_game or
   country), or filtered to one specific game/country. The score comes
   from `compute_score()` in score.py if that file/function exists;
   otherwise it falls back to the raw `engagement_rate` column.
3. Writes the insights to insights.txt
4. Uploads insights.txt to the running backend's POST /upload endpoint

The website's "Generate Insights" filters call the same insights_engine
logic directly through the backend, so the CLI and the UI always agree.

Run this AFTER the backend is up (see README instructions), e.g.:

    python workflow.py
    python workflow.py --top-n 10
    python workflow.py --top-n 5 --group-by primary_game
    python workflow.py --group-by country
    python workflow.py --top-n 10 --group-by primary_game --filter-value "League of Legends"
"""

import argparse
import os
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "backend" / "data" / "influencers.csv"
INSIGHTS_PATH = Path(__file__).resolve().parent / "insights.txt"

API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
UPLOAD_URL = f"{API_BASE}/upload"

# Make backend/insights_engine.py importable from here.
sys.path.insert(0, str(BASE_DIR / "backend"))
from insights_engine import (  # noqa: E402
    DEFAULT_TOP_N,
    GROUP_BY_CHOICES,
    compute_insights,
    load_rows,
)


# ---------------------------------------------------------------------------
# Write insights.txt
# ---------------------------------------------------------------------------
def write_insights(text: str, path: Path) -> None:
    path.write_text(text, encoding="utf-8")
    print(f"Wrote insights to {path}")


# ---------------------------------------------------------------------------
# Upload insights.txt to the backend
# ---------------------------------------------------------------------------
def upload_insights(path: Path, url: str) -> None:
    with open(path, "rb") as f:
        files = {"file": (path.name, f, "text/plain")}
        response = requests.post(url, files=files, timeout=10)

    if response.status_code == 200:
        print(f"Upload succeeded: {response.json()}")
    else:
        print(f"Upload failed ({response.status_code}): {response.text}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Generate influencer insights")
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Number of top influencers to include (default: {DEFAULT_TOP_N}). "
        "When --group-by is used, this applies per group (or to the "
        "filtered group, if --filter-value is given).",
    )
    parser.add_argument(
        "--group-by",
        choices=GROUP_BY_CHOICES,
        default="none",
        help="Show top-N within each primary_game or country group instead of "
        "one overall ranking (default: none)",
    )
    parser.add_argument(
        "--filter-value",
        default=None,
        help="When used with --group-by, restrict the output to just this one "
        'group value, e.g. --group-by primary_game --filter-value "Valorant"',
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    rows = load_rows(CSV_PATH)
    insights_text = compute_insights(
        rows,
        top_n=args.top_n,
        group_by=args.group_by,
        filter_value=args.filter_value,
    )
    write_insights(insights_text, INSIGHTS_PATH)
    upload_insights(INSIGHTS_PATH, UPLOAD_URL)


if __name__ == "__main__":
    main()
