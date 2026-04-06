# app/routers/recommendations.py

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List

from app import models
from app.deps import get_db
from app.services.career_engine import compute_careers_for_student
from app.auth.auth import get_current_active_user, require_roles
from app.projections.student_safe import project_student_safe

router = APIRouter(
    tags=["Recommendations"],
)


def compute_recommendations_payload(
    student_id: int, db: Session, lang: str = "en"
) -> dict:
    """Public wrapper — reused by assessments.py fallback. Backward compatible."""
    return _compute_recommendations_payload(student_id=student_id, db=db, lang=lang)


def _compute_recommendations_payload(
    student_id: int, db: Session, lang: str = "en"
) -> dict:
    """
    Computes RAW recommendations payload (includes numeric fields).
    Do NOT sanitize here. Sanitization applied in student endpoint only.
    """
    recommendations = compute_careers_for_student(
        student_id=student_id,
        db=db,
        limit=9,
        lang=lang,
        include_explainability=True,
        include_keyskills=True,
        include_clusters=True,
    )

    return {
        "student_id": student_id,
        "recommended_careers": recommendations,
    }


def _sanitize_recommendations_payload(payload: dict) -> dict:
    """
    Student-safe sanitization — removes numeric exposure at any depth.
    Preserves all string/text fields including new content fields.
    """

    def strip_numeric(obj):
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                key = str(k)
                if key in {
                    "score",
                    "weight",
                    "points",
                    "raw_score",
                    "scaled_score",
                    "top_keyskill_weights",
                }:
                    continue
                vv = strip_numeric(v)

                # Salary and market fields are safe to show students
                NUMERIC_WHITELIST = {
                    "salary_entry_inr",
                    "salary_mid_inr",
                    "salary_peak_inr",
                    "industry_growth_pct",
                }
                if key in NUMERIC_WHITELIST:
                    cleaned[key] = vv
                    continue

                # If the value is numeric (int/float) or a list of numerics, drop it
                if isinstance(vv, (int, float)):
                    continue
                if isinstance(vv, list) and vv and all(
                    isinstance(x, (int, float)) for x in vv
                ):
                    continue
                cleaned[key] = vv
            return cleaned

        if isinstance(obj, list):
            return [strip_numeric(x) for x in obj]

        return obj

    sanitized = strip_numeric(payload)

    for career in sanitized.get("recommended_careers", []) or []:
        if "matched_keyskills" in career and isinstance(
            career["matched_keyskills"], list
        ):
            for ks in career["matched_keyskills"]:
                if isinstance(ks, dict) and "weight" in ks:
                    ks.pop("weight", None)

        if "explainability" in career and isinstance(career["explainability"], list):
            for ex in career["explainability"]:
                if isinstance(ex, dict) and isinstance(ex.get("vars"), dict):
                    ex["vars"].pop("score", None)
                    ex["vars"].pop("top_keyskill_weights", None)

    return sanitized


@router.get("/{student_id}")
def get_recommendations(
    student_id: int,
    lang: str = Query("en", description="Language code: en (English) or kn (Kannada)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Get career recommendations for a student.
    Supports ?lang=en (default) or ?lang=kn for Kannada content.
    Falls back to English if Kannada not available for a career.
    """
    if current_user.role == "student":
        student_row = (
            db.query(models.Student)
            .filter(models.Student.user_id == current_user.id)
            .first()
        )
        if not student_row or student_row.id != student_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation forbidden",
            )

    payload = _compute_recommendations_payload(
        student_id=student_id, db=db, lang=lang
    )
    return project_student_safe(_sanitize_recommendations_payload(payload))


@router.get("/admin/{student_id}")
def get_recommendations_admin(
    student_id: int,
    lang: str = Query("en", description="Language code: en or kn"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles("admin", "counsellor")),
):
    """Admin view — returns raw payload including scores and all content fields."""
    return _compute_recommendations_payload(
        student_id=student_id, db=db, lang=lang
    )
