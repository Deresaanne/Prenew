"""
insights_engine.py

Shared insight-computation logic used by both:
  - backend/main.py     (the POST /insights/generate endpoint, for on-demand
                          generation triggered from the website's UI filters)
  - workflow/workflow.py (the standalone CLI script)

Keeping this logic in one place means the website and the CLI script always
rank and format influencers the exact same way.

Scoring: uses `compute_score()` (and optionally `prepare_context()` /
`WEIGHTS`) from workflow/score.py if available, otherwise falls back to
ranking by the raw `engagement_rate` column.
"""

import csv
import inspect
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

# ---------------------------------------------------------------------------
# Make workflow/score.py importable from here, regardless of which process
# (backend or workflow script) imports this module first.
# ---------------------------------------------------------------------------
_WORKFLOW_DIR = Path(__file__).resolve().parent.parent / "workflow"
if str(_WORKFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKFLOW_DIR))

DEFAULT_SCORE_FIELD = "engagement_rate"  # fallback ranking column
DEFAULT_TOP_N = 20
GROUP_BY_CHOICES = ["none", "primary_game", "country"]

try:
    from score import compute_score  # type: ignore
    _USING_CUSTOM_SCORE = True
except ImportError:
    compute_score = None
    _USING_CUSTOM_SCORE = False

try:
    from score import prepare_context  # type: ignore
except ImportError:
    prepare_context = None

try:
    from score import WEIGHTS as _SCORE_WEIGHTS  # type: ignore
except ImportError:
    _SCORE_WEIGHTS = None


def _default_score(row: dict, context=None) -> float:
    """Fallback scorer: just use the engagement_rate column."""
    try:
        return float(row.get(DEFAULT_SCORE_FIELD, 0.0))
    except (TypeError, ValueError):
        return 0.0


def get_score_fn():
    """Return (score_fn, label) -- the custom scorer if present, else the default."""
    if _USING_CUSTOM_SCORE and compute_score is not None:
        return compute_score, "custom score (score.py: compute_score)"
    return _default_score, f"default score ({DEFAULT_SCORE_FIELD})"


def _call_score_fn(fn, row: dict, context) -> float:
    """
    Call a scoring function whether it accepts (row) or (row, context).
    Lets score.py define compute_score(row) without a context argument too.
    """
    try:
        sig = inspect.signature(fn)
        accepts_context = len(sig.parameters) >= 2
    except (TypeError, ValueError):
        accepts_context = True  # best effort; fall back to 2-arg call

    if accepts_context:
        return fn(row, context)
    return fn(row)


# ---------------------------------------------------------------------------
# Load CSV
# ---------------------------------------------------------------------------
def load_rows(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found at {csv_path}")

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        raise ValueError("CSV file is empty")

    return rows


def unique_values(rows: list[dict], field: str) -> list[str]:
    """Sorted unique values of a column, e.g. every primary_game or country."""
    return sorted({(row.get(field) or "Unknown") for row in rows})


# ---------------------------------------------------------------------------
# Compute insights
# ---------------------------------------------------------------------------
def _score_all_rows(rows: list[dict], score_fn, context) -> list[tuple]:
    """Return a list of (row, score) tuples, one per row."""
    scored = []
    for row in rows:
        try:
            score = float(_call_score_fn(score_fn, row, context))
        except (TypeError, ValueError):
            score = 0.0
        scored.append((row, score))
    return scored


def _format_row_line(rank: int, row: dict, score: float) -> str:
    name = row.get("influencer_name", "Unknown")
    platform = row.get("platform", "N/A")
    game = row.get("primary_game", "N/A")
    country = row.get("country", "N/A")
    return (
        f"{rank:>2}. {name:<20} | {platform:<10} | "
        f"score: {score:>7.3f} | game: {game} | country: {country}"
    )


def _top_rows_without_tied_scores(
    ranked: list[tuple[dict, float]], top_n: int
) -> list[tuple[dict, float]]:
    cutoff = len(ranked)
    for index in range(1, len(ranked)):
        if ranked[index][1] == ranked[index - 1][1]:
            cutoff = index
            break
    return ranked[:min(top_n, cutoff)]


def compute_insights(
    rows: list[dict],
    top_n: int = DEFAULT_TOP_N,
    group_by: str = "none",
    filter_value: str | None = None,
) -> str:
    """
    Build the insights text.

    - group_by="none": overall top N across all rows.
    - group_by="primary_game"/"country", filter_value=None: top N within
      EVERY group (one section per game/country).
    - group_by="primary_game"/"country", filter_value=<a value>: top N
      within just that one group (e.g. only "League of Legends").
    """
    if group_by not in GROUP_BY_CHOICES:
        raise ValueError(f"group_by must be one of {GROUP_BY_CHOICES}")

    score_fn, score_label = get_score_fn()

    # If the custom scorer needs dataset-wide context (e.g. min/max for
    # normalization), build it once up front, over the whole dataset --
    # always over ALL rows, even when filtering to one group, so scores
    # stay comparable to the unfiltered ranking.
    context = None
    if _USING_CUSTOM_SCORE and prepare_context is not None:
        context = prepare_context(rows)

    scored_rows = _score_all_rows(rows, score_fn, context)
    all_scores = [score for _, score in scored_rows]

    lines = []
    lines.append("INFLUENCER ENGAGEMENT INSIGHTS")
    lines.append("=" * 40)
    lines.append(f"Total influencer records analyzed: {len(rows)}")
    lines.append(f"Ranking metric: {score_label}")

    if _USING_CUSTOM_SCORE and _SCORE_WEIGHTS:
        weight_str = ", ".join(f"{k}={v}" for k, v in _SCORE_WEIGHTS.items())
        lines.append(f"Weights: {weight_str}")

    lines.append(f"Average score: {mean(all_scores):.3f}")
    lines.append(f"Max score: {max(all_scores):.3f}")
    lines.append(f"Min score: {min(all_scores):.3f}")
    lines.append("")

    if group_by == "none":
        ranked = sorted(scored_rows, key=lambda pair: pair[1], reverse=True)
        top_rows = _top_rows_without_tied_scores(ranked, top_n)

        lines.append(f"TOP {top_n} INFLUENCERS BY SCORE")
        lines.append("-" * 40)
        for i, (row, score) in enumerate(top_rows, start=1):
            lines.append(_format_row_line(i, row, score))

    elif filter_value:
        # Top N within just the one requested group value
        filtered = [
            (row, score)
            for row, score in scored_rows
            if (row.get(group_by) or "Unknown") == filter_value
        ]
        ranked = sorted(filtered, key=lambda pair: pair[1], reverse=True)
        top_rows = _top_rows_without_tied_scores(ranked, top_n)

        lines.append(
            f"TOP {top_n} INFLUENCERS BY SCORE -- {group_by}: {filter_value} "
            f"({len(filtered)} total)"
        )
        lines.append("-" * 40)
        for i, (row, score) in enumerate(top_rows, start=1):
            lines.append(_format_row_line(i, row, score))

    else:
        # Group scored rows by the requested field (primary_game or country)
        groups = defaultdict(list)
        for row, score in scored_rows:
            key = row.get(group_by) or "Unknown"
            groups[key].append((row, score))

        lines.append(f"TOP {top_n} INFLUENCERS BY SCORE, GROUPED BY {group_by.upper()}")
        lines.append("-" * 40)

        for group_value in sorted(groups.keys()):
            group_rows = sorted(groups[group_value], key=lambda pair: pair[1], reverse=True)
            top_group_rows = _top_rows_without_tied_scores(group_rows, top_n)

            lines.append("")
            lines.append(f"{group_by}: {group_value}  ({len(groups[group_value])} total)")
            for i, (row, score) in enumerate(top_group_rows, start=1):
                lines.append(_format_row_line(i, row, score))

    return "\n".join(lines) + "\n"
