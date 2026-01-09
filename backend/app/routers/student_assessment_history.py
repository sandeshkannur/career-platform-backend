# app/routers/student_assessment_history.py

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_db
from app.auth.auth import get_current_active_user

router = APIRouter(
    tags=["Students"],
)

@router.get(
    "/students/{id}/assessments",
    response_model=schemas.StudentAssessmentHistoryResponse,
)
def get_student_assessment_history(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    B11: List past assessment attempts for a student (history view).

    Rules:
    - Student can only access their own student record (ownership enforced via students.user_id).
    - Data source: assessments table only (linked via assessments.user_id == current_user.id).
    - Ordered by submitted_at DESC.
    - Read-only. No pagination.
    """

    # 1) Validate student exists
    student = db.query(models.Student).filter(models.Student.id == id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    # 2) Ownership enforcement (same pattern as B10)
    if student.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this student's assessments",
        )

    # 3) Fetch assessments for current user (NOT by student_id)
    assessments = (
        db.query(models.Assessment)
        .filter(models.Assessment.user_id == current_user.id)
        .order_by(models.Assessment.submitted_at.desc())
        .all()
    )

    # 4) Map to response schema (assessment_version/status absent in DB => None)
    items: List[schemas.StudentAssessmentHistoryItem] = [
        schemas.StudentAssessmentHistoryItem(
            assessment_id=a.id,
            submitted_at=a.submitted_at,
            assessment_version=None,         # not present in current model
            scoring_config_version="v1",     # required default
            status=None,                     # not present in current model
        )
        for a in assessments
    ]

    # 5) Edge case: no history
    message: Optional[str] = None
    if len(items) == 0:
        message = "No assessment history found"

    return schemas.StudentAssessmentHistoryResponse(
        student_id=id,
        total_assessments=len(items),
        assessments=items,
        message=message,
    )
