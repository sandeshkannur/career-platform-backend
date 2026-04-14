"""
SME Weighted Aggregation Service.

Aggregates approved SME submissions for a given career into per-AQ
weighted averages, with outlier detection and consensus scoring.

Analysis-only — NO writes to scoring tables. Results are returned as
a dict for the caller (admin endpoint) to return or store as needed.

Algorithm summary
-----------------
1.  Load all sme_submissions with status='approved' for the career.
2.  For each submission, resolve credential_weight from the linked
    sme_profiles.credentials_score (default 1.0 if unlinked or null).
3.  For each AQ key (aq_01 … aq_25):
    a.  Collect all (rating, weight) pairs across SMEs.
    b.  Compute group median.
    c.  Compute population std_dev.
    d.  Mark outliers: abs(rating − median) > OUTLIER_STD_MULTIPLIER × std_dev.
    e.  Compute weighted average of non-outlier ratings using credential weights.
        If ALL ratings are outliers (edge case), fall back to unweighted mean.
    f.  Record per-AQ stats.
4.  consensus_score = 1 − (mean_std_dev / MAX_RATING), clamped to [0, 1].
    MAX_RATING = 10 (the maximum a single SME can submit) acts as the
    normalisation constant — the worst-case std_dev for a 0–10 scale is 5,
    but using MAX_RATING keeps the formula simple and conservative.
5.  Return structured result dict.

Rating scale: SME inputs integers 0–10. This service works on the raw
integer values extracted from submission_data JSON.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import SMESubmission, SMEProfile

# ── Constants ─────────────────────────────────────────────────────────────
AQ_KEYS: List[str] = [f"aq_{i:02d}" for i in range(1, 26)]   # aq_01 … aq_25
OUTLIER_STD_MULTIPLIER: float = 2.0   # |rating − median| > 2σ → outlier
MAX_RATING: float = 10.0              # upper bound of SME rating scale
MIN_APPROVED: int = 3                 # enforced by the endpoint, not here


# ── Helpers ───────────────────────────────────────────────────────────────

def _median(values: List[float]) -> float:
    return statistics.median(values)


def _pop_std(values: List[float]) -> float:
    """Population std_dev (σ). Returns 0.0 for single-element lists."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def _weighted_mean(pairs: List[Tuple[float, float]]) -> Optional[float]:
    """
    Weighted mean from (value, weight) pairs.
    Returns None on empty input or zero total weight.
    """
    if not pairs:
        return None
    total_weight = sum(w for _, w in pairs)
    if total_weight == 0:
        return None
    return sum(v * w for v, w in pairs) / total_weight


def _extract_rating(submission_data: Any, aq_key: str) -> Optional[float]:
    """
    Pull a numeric AQ rating out of submission_data.
    Handles both "aq_01" and "AQ_01" key formats.
    Returns None if the key is absent or non-numeric.
    """
    if not isinstance(submission_data, dict):
        return None
    raw = submission_data.get(aq_key) or submission_data.get(aq_key.upper())
    if raw is None:
        return None
    try:
        val = float(raw)
        # Clamp to valid range
        return max(0.0, min(MAX_RATING, val))
    except (TypeError, ValueError):
        return None


# ── Public API ────────────────────────────────────────────────────────────

def aggregate_career_submissions(db: Session, career_id: int) -> Dict[str, Any]:
    """
    Aggregate approved SME submissions for *career_id*.

    Returns
    -------
    {
        "career_id": int,
        "sme_count": int,              # total approved submissions used
        "outlier_count": int,          # total (submission × AQ) pairs flagged
        "consensus_score": float,      # 0.0–1.0 (higher = more agreement)
        "aq_aggregations": [
            {
                "aq_key":          str,    # "aq_01" … "aq_25"
                "weighted_avg":    float,  # credential-weighted mean (outliers excluded)
                "median":          float,
                "std_dev":         float,
                "sme_count":       int,    # submissions that had this AQ key
                "outlier_count":   int,    # ratings excluded from weighted_avg
            },
            …
        ],
    }

    Raises
    ------
    ValueError  if fewer than MIN_APPROVED (3) approved submissions exist.
    """
    # ── 1. Load approved submissions ──────────────────────────────────────
    submissions: List[SMESubmission] = (
        db.query(SMESubmission)
        .filter(
            SMESubmission.career_id == career_id,
            SMESubmission.status == "approved",
        )
        .all()
    )

    if len(submissions) < MIN_APPROVED:
        raise ValueError(
            f"Career {career_id} has only {len(submissions)} approved submission(s). "
            f"Minimum required: {MIN_APPROVED}."
        )

    # ── 2. Resolve credential weights per submission ──────────────────────
    # credential_weight = sme_profiles.credentials_score if linked, else 1.0
    weights: List[float] = []
    for sub in submissions:
        w = 1.0
        if sub.sme_id is not None:
            profile: Optional[SMEProfile] = (
                db.query(SMEProfile)
                .filter(SMEProfile.id == sub.sme_id)
                .first()
            )
            if profile is not None and profile.credentials_score is not None:
                w = max(0.0, float(profile.credentials_score))
                # Avoid zero-weight (unscored SME treated as default weight)
                if w == 0.0:
                    w = 1.0
        weights.append(w)

    # ── 3. Per-AQ aggregation ─────────────────────────────────────────────
    aq_aggregations: List[Dict[str, Any]] = []
    all_std_devs: List[float] = []
    total_outlier_count = 0

    for aq_key in AQ_KEYS:
        # Gather (rating, credential_weight) for submissions that have this key
        rated_pairs: List[Tuple[float, float]] = []
        for sub, w in zip(submissions, weights):
            rating = _extract_rating(sub.submission_data, aq_key)
            if rating is not None:
                rated_pairs.append((rating, w))

        if not rated_pairs:
            # AQ not present in any submission — record nulls
            aq_aggregations.append({
                "aq_key":        aq_key,
                "weighted_avg":  None,
                "median":        None,
                "std_dev":       None,
                "sme_count":     0,
                "outlier_count": 0,
            })
            continue

        ratings_only = [r for r, _ in rated_pairs]
        med = _median(ratings_only)
        std = _pop_std(ratings_only)
        threshold = OUTLIER_STD_MULTIPLIER * std

        # Separate inliers and outliers
        inlier_pairs: List[Tuple[float, float]] = []
        outlier_n = 0
        for r, w in rated_pairs:
            if std > 0 and abs(r - med) > threshold:
                outlier_n += 1
            else:
                inlier_pairs.append((r, w))

        total_outlier_count += outlier_n

        # Weighted average of inliers; fall back to all-ratings if all were outliers
        if inlier_pairs:
            w_avg = _weighted_mean(inlier_pairs)
        else:
            # Edge case: every rating is an outlier — use unweighted mean of all
            w_avg = sum(ratings_only) / len(ratings_only)

        all_std_devs.append(std)

        aq_aggregations.append({
            "aq_key":        aq_key,
            "weighted_avg":  round(w_avg, 4) if w_avg is not None else None,
            "median":        round(med, 4),
            "std_dev":       round(std, 4),
            "sme_count":     len(rated_pairs),
            "outlier_count": outlier_n,
        })

    # ── 4. Consensus score ────────────────────────────────────────────────
    # consensus = 1 − (mean_std_dev / MAX_RATING), clamped to [0, 1]
    # A perfectly-agreeing panel (std=0 for all AQs) → 1.0.
    # Maximum disagreement (mean_std_dev ≈ MAX_RATING) → near 0.
    if all_std_devs:
        mean_std_dev = sum(all_std_devs) / len(all_std_devs)
        consensus_score = max(0.0, min(1.0, 1.0 - (mean_std_dev / MAX_RATING)))
    else:
        consensus_score = 0.0

    return {
        "career_id":       career_id,
        "sme_count":       len(submissions),
        "outlier_count":   total_outlier_count,
        "consensus_score": round(consensus_score, 4),
        "aq_aggregations": aq_aggregations,
    }
