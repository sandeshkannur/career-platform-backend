# backend/app/services/analytics_orchestrator_service.py

"""
B9: Internal Analytics Orchestrator Service (NO public endpoint)

Purpose:
- Recompute dashboard-ready analytics snapshots after assessment completion.
- Must run AFTER B8 has successfully synced keyskill scores for a student.

Reads:
- student_keyskill_map (B8 output)

Writes:
- student_analytics_summary (JSONB snapshot)
  Unique (student_id, scoring_config_version) ensures idempotency.

Robustness:
- If no keyskill rows exist, return "nothing to recompute" (no exception).
- If one component fails, continue other components and capture warnings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app import models, schemas


# -----------------------------
# Deterministic thresholds
# -----------------------------
# scaled_0_100 score bands:
#   0–39   => Low
#   40–69  => Medium
#   70–100 => High
LOW_MAX = 39.0
MEDIUM_MAX = 69.0


def _bucket_for_score(score: float) -> str:
    """Deterministically map a score into a dashboard bucket."""
    if score <= LOW_MAX:
        return "low"
    if score <= MEDIUM_MAX:
        return "medium"
    return "high"


def recompute_student_analytics(
    db: Session,
    student_id: int,
    scoring_config_version: str = "v1",
) -> schemas.AnalyticsResult:
    """
    Entry point required by B9.

    Idempotent:
    - Upserts one row per (student_id, scoring_config_version).
    - Safe for reruns; overwrites payload_json and computed_at.

    IMPORTANT:
    - student_id refers to students.id (student profile).
    """
    warnings: List[str] = []
    computed_at = datetime.now(timezone.utc)

    # -----------------------------
    # Sanity check: student exists
    # -----------------------------
    student_exists = (
        db.query(models.Student.id)
        .filter(models.Student.id == student_id)
        .first()
    )
    if not student_exists:
        return schemas.AnalyticsResult(
            student_id=student_id,
            scoring_config_version=scoring_config_version,
            computed_at=computed_at,
            summary_row_upserted=False,
            keyskills_found=0,
            warnings=[f"student_id={student_id} not found; analytics not computed"],
            payload_preview=None,
        )

    # --------------------------------------
    # Read source rows from student_keyskill_map (B8 output)
    # --------------------------------------
    try:
        # NOTE:
        # student_keyskill_map does NOT have scoring_config_version in your current schema.
        # Versioning is applied at the analytics summary snapshot level only.
        rows = (
            db.query(models.StudentKeySkillMap)
            .filter(models.StudentKeySkillMap.student_id == student_id)
            .all()
        )
    except Exception as e:
        return schemas.AnalyticsResult(
            student_id=student_id,
            scoring_config_version=scoring_config_version,
            computed_at=computed_at,
            summary_row_upserted=False,
            keyskills_found=0,
            warnings=[f"failed to read student_keyskill_map: {repr(e)}"],
            payload_preview=None,
        )

    if not rows:
        # No data is not an error; just nothing to compute yet.
        return schemas.AnalyticsResult(
            student_id=student_id,
            scoring_config_version=scoring_config_version,
            computed_at=computed_at,
            summary_row_upserted=False,
            keyskills_found=0,
            warnings=[
                f"no student_keyskill_map rows for student_id={student_id}, version={scoring_config_version}"
            ],
            payload_preview={
                "overall_keyskill_summary": {"count": 0, "avg_score": None, "top_keyskills": []},
                "distribution": {"low": 0, "medium": 0, "high": 0},
                "meta": {
                    "student_id": student_id,
                    "scoring_config_version": scoring_config_version,
                    "computed_at": computed_at.isoformat(),
                },
            },
        )

    # --------------------------------------
    # Compute deterministic analytics payload
    # --------------------------------------
    payload: Dict[str, Any] = {
        "meta": {
            "student_id": student_id,
            "scoring_config_version": scoring_config_version,
            "computed_at": computed_at.isoformat(),
        },
        "overall_keyskill_summary": {},
        "distribution": {"low": 0, "medium": 0, "high": 0},
        "top_keyskills": [],
    }

    # Extract (keyskill_id, score)
    scores: List[Tuple[int, float]] = []
    try:
        for r in rows:
            keyskill_id = getattr(r, "keyskill_id")
            # IMPORTANT: Use the correct score field.
            # Your current StudentKeySkillMap shows "score".
            # If B8 uses a different numeric field (e.g., scaled_0_100), update ONLY here.
            score = float(getattr(r, "score") if getattr(r, "score") is not None else 100.0)
            scores.append((keyskill_id, score))
    except Exception as e:
        warnings.append(f"failed to extract keyskill scores: {repr(e)}")
        scores = []

    keyskills_found = len(scores)

    # 1) Distribution buckets
    try:
        for _, s in scores:
            payload["distribution"][_bucket_for_score(s)] += 1
    except Exception as e:
        warnings.append(f"failed to compute distribution buckets: {repr(e)}")

    # 2) Top-N keyskills (deterministic: score desc, keyskill_id asc)
    TOP_N = 5
    try:
        top_sorted = sorted(scores, key=lambda x: (-x[1], x[0]))[:TOP_N]
        payload["top_keyskills"] = [{"keyskill_id": ks_id, "score": round(sc, 2)} for ks_id, sc in top_sorted]
    except Exception as e:
        warnings.append(f"failed to compute top_keyskills: {repr(e)}")

    # 3) Overall summary (count + avg)
    try:
        avg_score = round(sum(s for _, s in scores) / len(scores), 2) if scores else None
        payload["overall_keyskill_summary"] = {"count": keyskills_found, "avg_score": avg_score, "top_n": TOP_N}
    except Exception as e:
        warnings.append(f"failed to compute overall_keyskill_summary: {repr(e)}")

    # --------------------------------------
    # Persist snapshot (idempotent upsert)
    # --------------------------------------
    summary_row_upserted = False
    try:
        stmt = insert(models.StudentAnalyticsSummary).values(
            student_id=student_id,
            scoring_config_version=scoring_config_version,
            payload_json=payload,
            computed_at=computed_at,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_student_analytics_student_version",
            set_={
                "payload_json": payload,
                "computed_at": computed_at,
            },
        )
        db.execute(stmt)
        db.commit()
        summary_row_upserted = True
    except Exception as e:
        db.rollback()
        warnings.append(f"failed to upsert student_analytics_summary: {repr(e)}")

    payload_preview = {
        "overall_keyskill_summary": payload.get("overall_keyskill_summary"),
        "distribution": payload.get("distribution"),
        "top_keyskills": payload.get("top_keyskills"),
        "meta": payload.get("meta"),
    }

    return schemas.AnalyticsResult(
        student_id=student_id,
        scoring_config_version=scoring_config_version,
        computed_at=computed_at,
        summary_row_upserted=summary_row_upserted,
        keyskills_found=keyskills_found,
        warnings=warnings,
        payload_preview=payload_preview,
    )
