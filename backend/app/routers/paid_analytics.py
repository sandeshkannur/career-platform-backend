# app/routers/paid_analytics.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import deps, schemas
from app.auth.auth import require_admin_or_counsellor

from app.services.explanations import build_full_explanation
from app.services.scoring import (
    compute_career_scores,
    compute_cluster_scores,
    get_student_keyskill_scores,
)

router = APIRouter(
    prefix="/paid-analytics",
    tags=["Paid Analytics"],
    dependencies=[Depends(require_admin_or_counsellor)],
)


@router.get("/{student_id}", response_model=schemas.PaidAnalyticsResponse)
def get_paid_analytics(student_id: int, db: Session = Depends(deps.get_db)):
    """
    Premium analytics:
    Uses:
      - Weighted career scoring
      - Cluster scoring (max career score)
      - Top contributing keyskills
      - Natural-language explanations
    """

    # 1) Fetch keyskills the student has
    student_keyskills = get_student_keyskill_scores(db, student_id)

    if not student_keyskills:
        # Student has no keyskills mapped → no scoring possible
        return schemas.PaidAnalyticsResponse(
            student_id=student_id,
            clusters=[],
            careers=[],
            cluster_scores={},
            career_scores={},
            keyskill_scores={},
            message="No key skills mapped for this student."
        )

    # 2) Compute weighted career + cluster scores
    career_scores = compute_career_scores(db, student_id)
    cluster_scores = compute_cluster_scores(db, career_scores)

    # 3) Build explanations (clusters + careers)
    explanation_data = build_full_explanation(db, student_id)

    # 4) Build final API response
    return schemas.PaidAnalyticsResponse(
        student_id=student_id,
        clusters=explanation_data["clusters"],
        careers=explanation_data["careers"],
        cluster_scores=cluster_scores,
        career_scores=career_scores,
        keyskill_scores=student_keyskills,
        message=None,
    )
