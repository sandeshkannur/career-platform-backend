# app/routers/recommendations.py

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional

from app import models
from app.deps import get_db
from app.services.career_engine import compute_careers_for_student
from app.auth.auth import get_current_active_user, require_roles
from app.projections.student_safe import project_student_safe

router = APIRouter(tags=["Recommendations"])


# ─── Sanitization ────────────────────────────────────────────────────────────

def _strip_numeric(obj):
    if isinstance(obj, dict):
        BLOCKED = {"score", "weight", "points", "raw_score", "scaled_score", "top_keyskill_weights"}
        cleaned = {}
        for k, v in obj.items():
            if str(k) in BLOCKED:
                continue
            vv = _strip_numeric(v)
            if isinstance(vv, (int, float)):
                continue
            if isinstance(vv, list) and vv and all(isinstance(x, (int, float)) for x in vv):
                continue
            cleaned[k] = vv
        return cleaned
    if isinstance(obj, list):
        return [_strip_numeric(x) for x in obj]
    return obj


def _sanitize_recommendations_payload(payload: dict) -> dict:
    """Keep this name — imported by assessments router during submit."""
    sanitized = _strip_numeric(payload)
    for career in sanitized.get("recommended_careers", []) or []:
        if "matched_keyskills" in career and isinstance(career["matched_keyskills"], list):
            for ks in career["matched_keyskills"]:
                if isinstance(ks, dict):
                    ks.pop("weight", None)
        if "explainability" in career and isinstance(career["explainability"], list):
            for ex in career["explainability"]:
                if isinstance(ex, dict) and isinstance(ex.get("vars"), dict):
                    ex["vars"].pop("score", None)
                    ex["vars"].pop("top_keyskill_weights", None)
    return sanitized


# ─── Core live compute (all 3 layers: psychometric + interest + context) ─────

def _compute_recommendations_payload(
    student_id: int,
    db: Session,
    limit: int = 9,
    lang: str = "en",
) -> dict:
    """
    Live recompute — always applies all available scoring layers:
      Layer 1: Psychometric scores from student_keyskill_map (written by B8 at submit)
      Layer 2: Interest inventory boosts from interest_inventory_responses
      Layer 3: Context/HSI already baked into student_keyskill_map scores by B7/B8

    This is the single source of truth for recommendations.
    """
    recommendations = compute_careers_for_student(
        student_id=student_id,
        db=db,
        limit=limit,
        lang=lang,
        include_explainability=True,
        include_keyskills=True,
        include_clusters=True,
    )
    return {
        "student_id": student_id,
        "recommended_careers": recommendations,
    }


# Keep this alias — used by assessments router
compute_recommendations_payload = _compute_recommendations_payload


# ─── Student endpoint ─────────────────────────────────────────────────────────

@router.get("/{student_id}")
def get_recommendations(
    student_id: int,
    lang: str = Query("en", description="Career content language: en or kn"),
    limit: int = Query(9, description="Number of careers (max 9 for students)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Live career recommendations applying all scoring layers:
    psychometric scores + interest inventory boosts + context/HSI.
    Returns student-safe sanitized output (no raw scores).
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

    safe_limit = min(max(1, limit), 9)
    payload = _compute_recommendations_payload(
        student_id=student_id,
        db=db,
        limit=safe_limit,
        lang=lang,
    )
    return project_student_safe(_sanitize_recommendations_payload(payload))


# ─── Admin endpoint ───────────────────────────────────────────────────────────

@router.get("/admin/{student_id}")
def get_recommendations_admin(
    student_id: int,
    lang: str = Query("en"),
    limit: int = Query(9),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles("admin", "counsellor")),
):
    """
    Admin: live recompute with raw scores visible (not sanitized).
    Shows exact scores so you can verify interest boost is working.
    """
    return _compute_recommendations_payload(
        student_id=student_id,
        db=db,
        limit=limit,
        lang=lang,
    )
