# app/routers/paid_analytics.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import deps, schemas
from app.auth.auth import require_admin_or_counsellor, require_role
from app.projections.student_safe import project_student_safe

from app.services.explanations import build_full_explanation
from app.services.scoring import (
    compute_career_scores,
    compute_cluster_scores,
    get_student_keyskill_scores,
)

router = APIRouter(
    prefix="/paid-analytics",
    tags=["Paid Analytics"],
)

def _strip_numbers_for_student(payload: dict) -> dict:
    """
    PR37: student/parent-safe projection.
    Removes any numeric analytics fields.
    Students see only fit bands + CMS-driven narrative blocks.
    """
    payload.pop("cluster_scores", None)
    payload.pop("career_scores", None)
    payload.pop("keyskill_scores", None)

    # Also remove per-item numeric scores if present
    for c in payload.get("clusters", []) or []:
        c.pop("score", None)
        c.pop("band_breakdown", None)  # breakdown can imply numeric proportions

    for c in payload.get("careers", []) or []:
        c.pop("score", None)

    return payload

@router.get(
    "/{student_id}",
    response_model=schemas.PaidAnalyticsResponse,
    dependencies=[Depends(require_admin_or_counsellor)],
)
def get_paid_analytics(
    student_id: int,
    version: str = "v1",
    locale: str = "en",
    db: Session = Depends(deps.get_db),
):
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
    explanation_data = build_full_explanation(
        db,
        student_id,
        version=version,
        locale=locale,
        allow_numbers_in_text=True,
    )

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
@router.get(
    "/{student_id}/student",
    response_model=schemas.PaidAnalyticsStudentResponse,
    dependencies=[Depends(require_role("student"))],
)
def get_paid_analytics_student(
    student_id: int,
    version: str = "v1",
    locale: str = "en",
    db: Session = Depends(deps.get_db),
):
    """
    PR37 student-safe paid insights:
    - NO numeric analytics
    - NO percentages
    - NO weights
    - Only fit bands + CMS-driven blocks
    """

    # 1) Fetch keyskills the student has
    student_keyskills = get_student_keyskill_scores(db, student_id)
    if not student_keyskills:
        return schemas.PaidAnalyticsStudentResponse(
            student_id=student_id,
            clusters=[],
            careers=[],
            message="No key skills mapped for this student.",
        )

    # 2) Build explanations (clusters + careers) — computed as before
    explanation_data = build_full_explanation(
        db,
        student_id,
        version=version,
        locale=locale,
        allow_numbers_in_text=False,
    )

    # 3) Project to student-safe shape (drop numeric fields)
    clusters_student = []
    for c in explanation_data.get("clusters", []) or []:
        clusters_student.append(
            schemas.PaidClusterInsightStudent(
                cluster_id=c["cluster_id"],
                cluster_name=c["cluster_name"],
                top_keyskills=c.get("top_keyskills", []) or [],
                fit_band=c["fit_band"],
                explanation=c["explanation"],
            )
        )

    careers_student = []
    for c in explanation_data.get("careers", []) or []:
        careers_student.append(
            schemas.PaidCareerInsightStudent(
                career_id=c["career_id"],
                career_name=c["career_name"],
                top_keyskills=c.get("top_keyskills", []) or [],
                fit_band=c["fit_band"],
                explanation=c["explanation"],
            )
        )

    return schemas.PaidAnalyticsStudentResponse(
        student_id=student_id,
        clusters=clusters_student,
        careers=careers_student,
        message=None,
    )
