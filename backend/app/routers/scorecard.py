# backend/app/routers/scorecard.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import text

from app import deps, models, schemas
from app.auth.auth import get_current_active_user

from app.services.scoring import (
    compute_career_scores,
    compute_cluster_scores,
    get_student_keyskill_scores,
)
from app.services.explanations import build_full_explanation
from app.services.tier_mapping import tier_to_score
from app.services.evidence import compute_assessment_evidence


router = APIRouter(
    prefix="/analytics/scorecard",
    tags=["Scorecard"],
    dependencies=[Depends(get_current_active_user)],
)


def reverse_tier(score: float) -> str:
    """
    Convert numeric 0–100 score back into your tier labels.
    """
    if score >= 90:
        return "Very High"
    if score >= 75:
        return "High"
    if score >= 55:
        return "Medium"
    if score >= 35:
        return "Low"
    return "Very Low"


@router.get("/{student_id}", response_model=schemas.ScorecardResponse)
def get_scorecard(student_id: int, db: Session = Depends(deps.get_db)):

    # PR5: Evidence computed-on-read from the latest assessment that has responses.
    # Authoritative linkage: students.user_id -> assessments.user_id -> assessment_responses.assessment_id
    latest_assessment_id = db.execute(
        text("""
            SELECT a.id
            FROM students s
            JOIN assessments a
              ON a.user_id = s.user_id
            JOIN assessment_responses ar
              ON ar.assessment_id = a.id
            WHERE s.id = :student_id
              AND s.user_id IS NOT NULL
            ORDER BY a.id DESC
            LIMIT 1
        """),
        {"student_id": student_id},
    ).scalar()

    evidence = None
    if latest_assessment_id is not None:
        evidence = compute_assessment_evidence(db, int(latest_assessment_id))

    # keyskill numeric scores (0–1.0), normalized
    sk_normalized = get_student_keyskill_scores(db, student_id)

    if not sk_normalized:
        return schemas.ScorecardResponse(
            student_id=student_id,
            clusters=[],
            careers=[],
            keyskills=[],
            cluster_scores={},
            career_scores={},
            evidence=evidence,
            message="No key skills mapped for this student."
        )

    # Convert normalized → numeric (0–100)
    sk_numeric = {ks_id: round(val * 100, 2) for ks_id, val in sk_normalized.items()}

    # Career + Cluster scoring
    career_scores = compute_career_scores(db, student_id)
    cluster_scores = compute_cluster_scores(db, career_scores)

    # Explanations (clusters + careers)
    explanation_data = build_full_explanation(db, student_id)

    # Prepare keyskill breakdown
    keyskills_db = db.query(models.KeySkill).all()
    ks_output = []

    for ks in keyskills_db:
        if ks.id not in sk_normalized:
            continue

        raw_score = sk_numeric[ks.id]
        norm = round(sk_normalized[ks.id], 3)
        tier = reverse_tier(raw_score)

        ks_output.append(schemas.KeySkillScore(
            keyskill_id=ks.id,
            name=ks.name,
            score=raw_score,
            normalized=norm,
            tier=tier,
            cluster_id=ks.cluster_id,
            cluster_name=ks.cluster.name if ks.cluster else None
        ))

    # Build final response
    return schemas.ScorecardResponse(
        student_id=student_id,
        clusters=explanation_data["clusters"],
        careers=explanation_data["careers"],
        keyskills=ks_output,
        cluster_scores=cluster_scores,
        career_scores=career_scores,
        evidence=evidence,
        message=None,
    )
