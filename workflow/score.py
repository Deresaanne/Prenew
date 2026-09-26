"""
score.py

Defines a custom scoring function used by workflow.py to rank influencers
on a composite of three dimensions, rather than raw follower count:

    Dimension            Metric used                Weight
    -------------------  --------------------------  ------
    Engagement quality   engagement_rate             0.5
    Brand fit            estimated_roi               0.3
    Audience/brand match brand_partnerships_count     0.2

The weights sum to 1.0, and each metric is rescaled to a comparable 0-1
range across the whole dataset before being combined, so the final score
is itself roughly in [0, 1] and reads like a percentage composite rather
than a mix of incomparable units (a % rate, a dollar-ish ROI figure, and
a small integer count).

Edit WEIGHTS below to change the balance between the three dimensions --
they should always sum to 1.0. Add/remove metrics by editing WEIGHTS and,
if needed, tweaking compute_score() to match.

workflow.py calls these two functions:
    prepare_context(rows)     -> called once with every CSV row, computes
                                 the min/max needed to normalize each metric
    compute_score(row, ctx)   -> called per row, returns the composite score

If this file is deleted, or if it doesn't define `compute_score`,
workflow.py falls back to ranking by the raw `engagement_rate` column.
"""

# ---------------------------------------------------------------------------
# Weights - must sum to 1.0
# ---------------------------------------------------------------------------
WEIGHTS = {
    "engagement_rate": 0.5,           # engagement quality
    "estimated_roi": 0.3,             # brand fit (return on brand spend)
    "brand_partnerships_count": 0.2,  # audience/brand match (partnership track record)
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "WEIGHTS must sum to 1.0"


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def prepare_context(rows: list[dict]) -> dict:
    """
    Called once by workflow.py before scoring, with every CSV row. Computes
    the min/max of each weighted metric across the whole dataset so
    compute_score() can rescale every row onto a comparable 0-1 scale.
    """
    context = {}
    for field in WEIGHTS:
        values = [_to_float(row.get(field)) for row in rows]
        context[field] = {"min": min(values), "max": max(values)}
    return context


def _normalize(value: float, field: str, context: dict) -> float:
    lo = context[field]["min"]
    hi = context[field]["max"]
    if hi == lo:
        return 0.5  # no spread in the data for this metric; treat as neutral
    return (value - lo) / (hi - lo)


def compute_score(row: dict, context: dict) -> float:
    """
    Weighted blend of three normalized metrics (each 0-1), combined with
    WEIGHTS (which sum to 1.0). The result lands in roughly [0, 1] and can
    be read as a composite "audience match / engagement / brand fit" score.
    """
    total = 0.0
    for field, weight in WEIGHTS.items():
        raw_value = _to_float(row.get(field))
        normalized = _normalize(raw_value, field, context)
        total += normalized * weight
    return total
