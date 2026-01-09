# app/routers/student_results_history.py

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_db
from app.auth.auth import get_current_active_user


router = APIRouter(tags=["Students"])


def _summarize_top_careers(recommended_careers: Any, limit: int = 5) -> Optional[List[Any]]:
    """
    Convert stored JSONB into a small 'top_careers' summary list.

    Handles common shapes:
    - list: return first N items
    - dict with a list field: tries keys like "top_careers", "careers", "recommendations"
    - dict otherwise: returns first N key-value pairs as small dicts
    """
    if recommended_careers is None:
        return None

    # Case 1: list
    if isinstance(recommended_careers, list):
        return recommended_careers[:limit]

    # Case 2: dict
    if isinstance(recommended_careers, dict):
        for key in ["top_careers", "careers", "recommendations", "topCareers"]:
            val = recommended_careers.get(key)
            if isinstance(val, list):
                return val[:limit]

        # Fallback: pick first N items from dict (stable order in Py3.7+)
        items = list(recommended_careers.items())[:limit]
        return [{k: v} for (k, v) in items]

    # Unknown shape
    return [recommended_careers]


@router.get(
    "/students/{id}/results",
    response_model=schemas.StudentResultHistoryResponse,
)
def get_student_results_history(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    # 1) Load student
    student = db.query(models.Student).filter(models.Student.id == id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    # 2) Ownership enforcement (same as B10/B11)
    if student.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this student's results",
        )

    # 3) Read-only query from assessment_results via assessments.user_id
    rows = (
        db.query(models.AssessmentResult)
        .join(models.Assessment, models.Assessment.id == models.AssessmentResult.assessment_id)
        .filter(models.Assessment.user_id == current_user.id)
        .order_by(models.AssessmentResult.generated_at.desc())
        .all()
    )

    # 4) Map to response schema
    results: List[schemas.StudentResultHistoryItem] = []
    for r in rows:
        results.append(
            schemas.StudentResultHistoryItem(
                result_id=r.id,
                assessment_id=r.assessment_id,
                generated_at=r.generated_at,
                assessment_version=None,              # not stored in your schema/table today
                scoring_config_version="v1",          # required default/version alignment
                recommended_stream=r.recommended_stream,
                top_careers=_summarize_top_careers(r.recommended_careers, limit=5),
                status=None,                          # not stored today
            )
        )

    message = None
    if len(results) == 0:
        message = "No results found"

    return schemas.StudentResultHistoryResponse(
        student_id=student.id,
        total_results=len(results),
        results=results,
        message=message,
    )
