# app/routers/student_results_history.py

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from app import models, schemas
from app.deps import get_db
from app.auth.auth import get_current_active_user
from app.services.evidence import compute_assessment_evidence


router = APIRouter(tags=["Students"])

# Global-ready: map any seeded/prose explainability text to stable keys.
# Later, these keys should come directly from scoring/explainability services.
EXPLAINABILITY_TEXT_TO_KEYS = {
    "This recommendation is based on patterns across your responses.": "EXP_PATTERN_MATCH",
    "It aligns with the kinds of tasks and thinking styles common in this career.": "EXP_ROLE_ALIGNMENT",
    "This is suggested because your profile matches multiple aspects of the role.": "EXP_MULTI_SIGNAL_MATCH",
    "You can build even stronger alignment by developing a few supporting skills.": "EXP_GROW_WITH_PRACTICE",
    "This appears as a promising option to explore.": "EXP_PROMISING_TO_EXPLORE",
    "Trying beginner-friendly activities in this area will help validate your interest.": "EXP_TRY_SMALL_PROJECTS",
}


def _normalize_career_item(item: Any) -> Any:
    """
    Additive normalization for career items to support i18n/global rollout.
    - Keeps existing 'explainability' text.
    - Adds 'explainability_keys' when possible.
    """
    if not isinstance(item, dict):
        return item

    texts = item.get("explainability")

      # Support both legacy list[str] and newer list[dict] / str / dict shapes
    if isinstance(texts, list):
          keys: List[str] = []
          for t in texts:
              if isinstance(t, str):
                  k = EXPLAINABILITY_TEXT_TO_KEYS.get(t)
                  if k:
                      keys.append(k)
              elif isinstance(t, dict):
                  # Prefer explicit key if present
                  k = t.get("key") or t.get("explainability_key")
                  if not k:
                      txt = t.get("text") or t.get("value") or ""
                      k = EXPLAINABILITY_TEXT_TO_KEYS.get(txt)
                  if k:
                      keys.append(k)
          if keys:
              item["explainability_keys"] = keys

    elif isinstance(texts, dict):
          k = texts.get("key") or texts.get("explainability_key")
          if not k:
              txt = texts.get("text") or texts.get("value") or ""
              k = EXPLAINABILITY_TEXT_TO_KEYS.get(txt)
          if k:
              item["explainability_keys"] = [k]

    elif isinstance(texts, str):
          k = EXPLAINABILITY_TEXT_TO_KEYS.get(texts)
          if k:
              item["explainability_keys"] = [k]

    return item

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
        sliced = recommended_careers[:limit]
        return [_normalize_career_item(x) for x in sliced]

    # Case 2: dict
    if isinstance(recommended_careers, dict):
        for key in ["top_careers", "careers", "recommendations", "topCareers"]:
            val = recommended_careers.get(key)
            if isinstance(val, list):
                sliced = val[:limit]
                return [_normalize_career_item(x) for x in sliced]

        # Fallback: pick first N items from dict (stable order in Py3.7+)
        items = list(recommended_careers.items())[:limit]
        return [{k: v} for (k, v) in items]

    # Unknown shape
    return [_normalize_career_item(recommended_careers)]


def _build_blocks_for_result(top_careers: list, *, db: Session = None, assessment_id: Optional[int] = None, career_limit: int = 3) -> list:

    """
    Build extensible result blocks.
    - Student-safe: no numbers, only safe text/keys.
    - Backward compatible: uses existing `top_careers` value.
    """
    blocks = []

    # TOP_CAREERS block (always present)
    blocks.append(
        schemas.TopCareersBlock(
            items=top_careers or [],
            limit=career_limit,
        )
    )

    # If no careers exist, include a deterministic empty state block for UI
    if not top_careers:
        blocks.append(schemas.EmptyStateBlock())
        return blocks

    # Premium blocks (computed-on-read; additive only)
    facet_keys: List[str] = []
    aq_keys: List[str] = []

    # Best-effort evidence resolution (never break the endpoint)
    if db is not None and assessment_id:
        try:
            ev = compute_assessment_evidence(db, int(assessment_id))

            facet_keys = [x["facet_code"] for x in (ev.get("facet_evidence") or [])[:5] if x.get("facet_code")]
            aq_keys = [x["aq_code"] for x in (ev.get("aq_evidence_summary") or [])[:5] if x.get("aq_code")]
        except Exception:
            facet_keys = []
            aq_keys = []

    blocks.append(
        schemas.FacetInsightsBlock(
            facet_keys=facet_keys,
        )
    )
    blocks.append(
        schemas.AssociatedQualitiesBlock(
            aq_keys=aq_keys,
        )
    )

    return blocks

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
        career_limit = 368 if (current_user.subscription_tier or "free").lower() == "premium" else 3
        top_careers = _summarize_top_careers(r.recommended_careers, limit=career_limit) or []

        results.append(
            schemas.StudentResultHistoryItem(
                result_id=r.id,
                assessment_id=r.assessment_id,
                generated_at=r.generated_at,
                assessment_version=None,              # not stored in your schema/table today
                scoring_config_version="v1",          # required default/version alignment
                recommended_stream=r.recommended_stream,
                top_careers=top_careers,
                results_payload_version="v1",
                blocks=_build_blocks_for_result(top_careers, db=db, assessment_id=r.assessment_id, career_limit=career_limit),
                status=None,                          # not stored today
            )
        )

    # 5) If no stored results exist, return a safe empty response
    if len(results) == 0:
        return schemas.StudentResultHistoryResponse(
            student_id=student.id,
            total_results=0,
            results=[],
            message="No stored or computed results found yet.",
        )

    # 6) Normal path: return stored results
    return schemas.StudentResultHistoryResponse(
        student_id=student.id,
        total_results=len(results),
        results=results,
        message=None,
    )

