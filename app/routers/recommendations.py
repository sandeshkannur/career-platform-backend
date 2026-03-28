# app/routers/recommendations.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app import models
from app.deps import get_db
from app.services.career_engine import compute_careers_for_student
from app.auth.auth import get_current_active_user, require_roles
from app.projections.student_safe import project_student_safe

router = APIRouter(
    tags=["Recommendations"],
    # NOTE: no auth dependency here to avoid 401 issues in Swagger for now
)

def compute_recommendations_payload(student_id: int, db: Session) -> dict:
    """
    Public wrapper for reuse outside this router (e.g., assessments fallback).
    Keeps existing behavior unchanged.
    """
    return _compute_recommendations_payload(student_id=student_id, db=db)


def _compute_recommendations_payload(student_id: int, db: Session) -> dict:
    """
    Computes RAW recommendations payload (includes numeric fields).
    Do NOT sanitize here. Sanitization is applied only in student endpoint.
    """
    recommendations = compute_careers_for_student(
        student_id=student_id,
        db=db,
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
    Student-safe sanitization:
    - Remove numeric exposure (scores, weights) from any depth.
    - Keep only student-safe semantic fields + explainability keys/vars (non-numeric).
    """

    def strip_numeric(obj):
        # Recursively remove numeric values and known numeric keys
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                key = str(k)

                # Hard block known numeric fields (even if stringified)
                if key in {
                    "score",
                    "weight",
                    "points",
                    "raw_score",
                    "scaled_score",
                    "top_keyskill_weights",
                }:
                    continue

                # Recurse
                vv = strip_numeric(v)

                # If the value is numeric (int/float) or a list of numerics, drop it
                if isinstance(vv, (int, float)):
                    continue
                if isinstance(vv, list) and vv and all(isinstance(x, (int, float)) for x in vv):
                    continue

                cleaned[key] = vv
            return cleaned

        if isinstance(obj, list):
            return [strip_numeric(x) for x in obj]

        return obj

    # 1) Strip numeric fields everywhere
    sanitized = strip_numeric(payload)

    # 2) Defense-in-depth: ensure matched_keyskills entries never include weight
    for career in sanitized.get("recommended_careers", []) or []:
        if "matched_keyskills" in career and isinstance(career["matched_keyskills"], list):
            for ks in career["matched_keyskills"]:
                if isinstance(ks, dict) and "weight" in ks:
                    ks.pop("weight", None)

        # Also protect explainability vars from known numeric keys
        if "explainability" in career and isinstance(career["explainability"], list):
            for ex in career["explainability"]:
                if isinstance(ex, dict) and isinstance(ex.get("vars"), dict):
                    ex["vars"].pop("score", None)
                    ex["vars"].pop("top_keyskill_weights", None)

    return sanitized


@router.get("/{student_id}")
def get_recommendations(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Get career recommendations for a student based on:

    StudentKeySkillMap -> KeySkill -> Career (via career_keyskill_association)
    """
    # Students can only access their own recommendations.
    # In this app, student linkage is via students.user_id (see /v1/auth/me).
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
    
    payload = _compute_recommendations_payload(student_id=student_id, db=db)

    # ✅ IMPORTANT: Student endpoint returns sanitized payload only
    return project_student_safe(_sanitize_recommendations_payload(payload))

    

@router.get("/admin/{student_id}")
def get_recommendations_admin(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles("admin", "counsellor")),
):
    # Reuse the same logic by calling the student route function body pattern
    # (We keep it simple: duplicate the call path by invoking the same compute pipeline)
    return _compute_recommendations_payload(student_id=student_id, db=db)
