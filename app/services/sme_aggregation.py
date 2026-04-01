"""
app/services/sme_aggregation.py

ADM-B03: SME Weighted Aggregation Engine.

Computes final calibrated AQ weights for a career+round from SME submissions.

Algorithm (Approach B — credentials × calibration composite):
  Step 1: Collect all submitted ratings for career+round
  Step 2: Per AQ — compute group median across all SME ratings
  Step 3: Per SME — compute calibration_score:
            calibration_score = 1 - mean(|rating_i - median_i|) for all 25 AQs
            Range: 0.0 (complete outlier) → 1.0 (perfect consensus alignment)
  Step 4: Per SME — compute effective_weight:
            effective_weight = credentials_score × calibration_score
            If credentials_score is None → treat as 0.5 (neutral)
  Step 5: Per AQ — compute final_weight:
            final_weight = Σ(rating_i × eff_weight_i) / Σ(eff_weight_i)
            Fallback to simple mean if all effective_weights are zero
  Step 6: Store results in career_aq_weights table (upsert by career+aq+round)
  Step 7: Update calibration_score on each SMEProfile

This service is called by POST /admin/sme/aggregate.
It does NOT write to the student scoring tables — that requires explicit
promotion via ADM-B16 (admin approval workflow).

Student code: this service never touches assessment_results,
student_skill_scores, or any assessment_* table.
"""
import logging
import statistics
from datetime import datetime, timezone
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

from app.models import (
    SMESubmissionToken,
    SMEAQRating,
    SMEProfile,
    CareerAQWeight,
)

logger = logging.getLogger(__name__)


# ============================================================
# Public entry point
# ============================================================

def run_aggregation(
    db:          Session,
    career_id:   int,
    round_number: int = 1,
) -> dict:
    """
    Run the full weighted aggregation pipeline for a career+round.

    Returns a summary dict with:
      - career_id, round_number
      - sme_count: number of SMEs who submitted for this career+round
      - aq_count: number of AQs computed (should always be 25)
      - weights: list of {aq_code, final_weight, median_rating, std_deviation, sme_count}
      - calibration_updates: list of {sme_id, old_score, new_score}
      - warnings: list of warning strings (e.g. too few SMEs)

    Raises ValueError if no submitted tokens found for career+round.
    """
    logger.info("ADM-B03: Starting aggregation — career=%s round=%s", career_id, round_number)

    # ── Step 1: Collect submitted tokens for this career+round ────────────
    tokens = db.query(SMESubmissionToken).filter(
        SMESubmissionToken.career_id    == career_id,
        SMESubmissionToken.round_number == round_number,
        SMESubmissionToken.status       == "submitted",
    ).all()

    if not tokens:
        raise ValueError(
            f"No submitted tokens found for career_id={career_id} round={round_number}. "
            "At least one SME must submit before aggregation can run."
        )

    warnings = []
    if len(tokens) < 3:
        warnings.append(
            f"Only {len(tokens)} SME(s) submitted. "
            "Minimum 3 recommended for reliable calibration. "
            "Results may not be statistically robust."
        )

    token_ids = [t.id for t in tokens]
    sme_ids   = list({t.sme_id for t in tokens})

    logger.info("ADM-B03: Found %s submitted tokens from %s SMEs", len(tokens), len(sme_ids))

    # ── Step 2: Load all AQ ratings for these tokens ──────────────────────
    ratings = db.query(SMEAQRating).filter(
        SMEAQRating.token_id.in_(token_ids)
    ).all()

    if not ratings:
        raise ValueError(f"No AQ ratings found for career_id={career_id} round={round_number}.")

    # Organise: ratings_by_aq[aq_code] = list of (sme_id, weight_rating)
    # Organise: ratings_by_sme[sme_id][aq_code] = weight_rating
    ratings_by_aq:  Dict[str, List[tuple]] = {}
    ratings_by_sme: Dict[int, Dict[str, float]] = {}

    for r in ratings:
        if r.aq_code not in ratings_by_aq:
            ratings_by_aq[r.aq_code] = []
        ratings_by_aq[r.aq_code].append((r.sme_id, r.weight_rating))

        if r.sme_id not in ratings_by_sme:
            ratings_by_sme[r.sme_id] = {}
        ratings_by_sme[r.sme_id][r.aq_code] = r.weight_rating

    aq_codes = sorted(ratings_by_aq.keys())
    logger.info("ADM-B03: %s unique AQ codes found", len(aq_codes))

    # ── Step 3: Compute group median per AQ ───────────────────────────────
    medians: Dict[str, float] = {}
    for aq_code, sme_ratings in ratings_by_aq.items():
        values = [rating for _, rating in sme_ratings]
        medians[aq_code] = statistics.median(values)

    # ── Step 4: Compute calibration_score per SME ─────────────────────────
    # calibration_score = 1 - mean(|rating - median|) across all rated AQs
    calibration_scores: Dict[int, float] = {}
    calibration_updates = []

    sme_profiles = {
        sme.id: sme
        for sme in db.query(SMEProfile).filter(SMEProfile.id.in_(sme_ids)).all()
    }

    for sme_id in sme_ids:
        sme_ratings = ratings_by_sme.get(sme_id, {})
        deviations = []
        for aq_code in aq_codes:
            if aq_code in sme_ratings and aq_code in medians:
                dev = abs(sme_ratings[aq_code] - medians[aq_code])
                deviations.append(dev)

        if deviations:
            calib = round(1.0 - statistics.mean(deviations), 4)
            calib = max(0.0, min(1.0, calib))  # clamp to [0,1]
        else:
            calib = 0.5  # neutral if no deviations computable

        calibration_scores[sme_id] = calib

        # Update SMEProfile.calibration_score
        sme = sme_profiles.get(sme_id)
        if sme:
            old_score = sme.calibration_score
            sme.calibration_score = calib
            calibration_updates.append({
                "sme_id":    sme_id,
                "sme_name":  sme.full_name,
                "old_score": old_score,
                "new_score": calib,
            })

    logger.info("ADM-B03: Calibration scores computed for %s SMEs", len(calibration_scores))

    # ── Step 5: Compute effective_weight per SME ──────────────────────────
    # effective_weight = credentials_score × calibration_score
    # credentials_score defaults to 0.5 if not set (neutral, not zero)
    effective_weights: Dict[int, float] = {}
    for sme_id in sme_ids:
        sme = sme_profiles.get(sme_id)
        cred = sme.credentials_score if (sme and sme.credentials_score is not None) else 0.5
        calib = calibration_scores.get(sme_id, 0.5)
        effective_weights[sme_id] = round(cred * calib, 4)

    # ── Step 6: Compute final_weight per AQ ───────────────────────────────
    # final_weight = Σ(rating_i × eff_weight_i) / Σ(eff_weight_i)
    # Fallback: simple mean if all effective_weights are zero
    weight_results = []

    for aq_code in aq_codes:
        sme_ratings = ratings_by_aq[aq_code]
        values      = [rating for _, rating in sme_ratings]

        # Weighted average
        numerator   = sum(r * effective_weights.get(sid, 0.5) for sid, r in sme_ratings)
        denominator = sum(effective_weights.get(sid, 0.5)     for sid, _ in sme_ratings)

        if denominator > 0:
            final_weight = round(numerator / denominator, 4)
        else:
            # Fallback to simple mean
            final_weight = round(statistics.mean(values), 4)
            warnings.append(f"AQ {aq_code}: effective weights all zero — using simple mean as fallback.")

        # Statistics for audit
        median_rating = round(medians[aq_code], 4)
        std_dev = round(statistics.stdev(values), 4) if len(values) > 1 else 0.0

        weight_results.append({
            "aq_code":       aq_code,
            "final_weight":  final_weight,
            "median_rating": median_rating,
            "std_deviation": std_dev,
            "sme_count":     len(sme_ratings),
        })

    # ── Step 7: Upsert into career_aq_weights ─────────────────────────────
    now = datetime.now(timezone.utc)
    upserted = 0

    for w in weight_results:
        existing = db.query(CareerAQWeight).filter(
            CareerAQWeight.career_id    == career_id,
            CareerAQWeight.aq_code      == w["aq_code"],
            CareerAQWeight.round_number == round_number,
        ).first()

        if existing:
            # Update existing row — re-running aggregation overwrites previous result
            existing.final_weight   = w["final_weight"]
            existing.median_rating  = w["median_rating"]
            existing.std_deviation  = w["std_deviation"]
            existing.sme_count      = w["sme_count"]
            existing.computed_at    = now
            # Never reset is_promoted if already promoted
        else:
            db.add(CareerAQWeight(
                career_id    = career_id,
                aq_code      = w["aq_code"],
                round_number = round_number,
                final_weight = w["final_weight"],
                median_rating= w["median_rating"],
                std_deviation= w["std_deviation"],
                sme_count    = w["sme_count"],
                is_promoted  = False,
                computed_at  = now,
            ))
            upserted += 1

    db.commit()
    logger.info("ADM-B03: Upserted %s career_aq_weights rows", upserted + (len(weight_results) - upserted))

    summary = {
        "career_id":            career_id,
        "round_number":         round_number,
        "sme_count":            len(sme_ids),
        "aq_count":             len(weight_results),
        "weights":              weight_results,
        "calibration_updates":  calibration_updates,
        "warnings":             warnings,
    }

    logger.info("ADM-B03: Aggregation complete — %s AQs computed, %s SMEs calibrated",
                len(weight_results), len(calibration_updates))
    return summary
