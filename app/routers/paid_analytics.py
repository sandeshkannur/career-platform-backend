# app/routers/paid_analytics.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import deps, schemas, models
from app.auth.auth import require_admin_or_counsellor, require_role, require_roles
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

@router.get(
    "/{student_id}/deep",
    dependencies=[Depends(require_roles("admin", "counsellor", "student"))],
)
def get_paid_analytics_deep_insights(
    student_id: int,
    result_id: int | None = None,
    version: str = "v1",
    locale: str = "en",
    db: Session = Depends(deps.get_db),
):
    """
    PR-C: Deep Insights (KEYS ONLY; student-safe; CMS-controlled)

    IMPORTANT:
    - This endpoint returns explanation KEYS (not final prose).
    - Frontend must resolve keys via /v1/content/explainability.
    - We keep it deterministic and non-judgmental.
    - RBAC: admin/counsellor/student allowed (premium gating can be tightened later).
    """

    # Reuse the already-deterministic explainability builder
    explanation_data = build_full_explanation(
        db,
        student_id,
        version=version,
        locale=locale,
        allow_numbers_in_text=False,
    )

    # Helper: map fit bands -> PR-C why keys (MVP)
    def _why_keys_for_band(fit_band: str) -> list[str]:
        """
        Map fit_band -> existing CMS explainability keys.
        These keys already exist in explainability_content (v1/en).
        """
        band = (fit_band or "").strip().lower()

        if band in {"high_potential", "high"}:
            return ["paid.career.high_potential"]
        if band in {"strong"}:
            return ["paid.career.strong"]
        if band in {"promising"}:
            return ["paid.career.promising"]
        if band in {"developing"}:
            return ["paid.career.developing"]
        if band in {"exploring"}:
            return ["paid.career.exploring"]

        return ["paid.career.exploring"]

    # Helper: cluster insight keys (MVP deterministic)
    def _cluster_insight_keys(cluster_item: dict) -> list[str]:
        """
        Map cluster evidence -> existing CMS keys.
        """
        top_ks = cluster_item.get("top_keyskills", []) or []
        if len(top_ks) > 0:
            return ["paid.cluster.with_keyskills"]
        return ["paid.cluster.no_keyskills"]

    # --- Cluster insights (take top 3 from computed explanation list) ---
    cluster_insights = []
    for c in (explanation_data.get("clusters", []) or [])[:3]:
        cluster_insights.append(
            {
                "cluster_title": c.get("cluster_name"),
                "insight_keys": _cluster_insight_keys(c),
            }
        )

    # --- Career insights (take top 3 from computed explanation list) ---
    career_insights = []
    for c in (explanation_data.get("careers", []) or [])[:3]:
        fit_band = c.get("fit_band") or "exploring"
        career_insights.append(
            {
                "career_id": c.get("career_id"),
                "career_title": c.get("career_name"),
                "fit_band_key": (fit_band or "").strip().lower(),
                "why_keys": _why_keys_for_band(fit_band),
                # MVP evidence: we only return empty arrays until we wire result-based facets/AQ keys
                "evidence": {"facet_keys": [], "aq_keys": []},
            }
        )

    # --- Next steps (generic keys; resolved by CMS) ---
    next_steps = {"keys": ["AQ.INTRO.001"]}

    return {
        "student_id": student_id,
        "result_id": result_id,
        "version": version,
        "locale": locale,
        "cluster_insights": cluster_insights,
        "career_insights": career_insights,
        "next_steps": next_steps,
    }

