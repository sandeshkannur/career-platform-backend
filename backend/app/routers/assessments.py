# app/routers/assessments.py

from typing import List, Dict

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    BackgroundTasks,
)
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_db
from app.auth.auth import get_current_active_user

# 🧠 Scoring logic for assessments (kept)
from app.utils.scoring import compute_skill_scores, assign_tiers, compute_cps_v1

# 🔥 Existing
from app.services.tier_mapping import apply_keyskill_tiers

# ✅ B7 scoring service (NEW)
from app.services.assessment_scoring_service import (
    compute_and_persist_skill_scores,
    EmptyResponsesError,
)

# ✅ B8 keyskill sync service (NEW)
from app.services.keyskill_sync_service import sync_skill_scores_to_keyskills

# ✅ B9 analytics orchestrator service (NEW - internal)
from app.services.analytics_orchestrator_service import recompute_student_analytics

# ✅ Step 5 fix: background task must create its own session
from app.database import SessionLocal


router = APIRouter(
    tags=["Assessments"],
)


# ----------------------------------------------------------
# 🚀 Start a new assessment
# ----------------------------------------------------------
@router.post(
    "/",
    response_model=schemas.AssessmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new assessment",
)
def create_assessment(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    assessment = models.Assessment(
    user_id=current_user.id,
    assessment_version="v1",
    scoring_config_version="v1",
)
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


# ----------------------------------------------------------
# 📝 Submit question responses
# ----------------------------------------------------------
@router.post(
    "/{assessment_id}/responses",
    response_model=List[schemas.AssessmentResponseOut],
    summary="Submit responses for an assessment",
)
def submit_responses(
    assessment_id: int,
    responses: List[schemas.AssessmentResponseCreate],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    assessment = db.query(models.Assessment).get(assessment_id)
    if not assessment or assessment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found"
        )

    saved = []
    for r in responses:
        resp = models.AssessmentResponse(
            assessment_id=assessment_id,
            question_id=r.question_id,
            answer=r.answer,
        )
        db.add(resp)
        saved.append(resp)

    db.commit()

    # ✅ Step 5 fix: Do NOT pass request-scoped db into background task
    background_tasks.add_task(generate_result, assessment_id, current_user.id)

    return saved


# ----------------------------------------------------------
# 📥 Manual trigger for score computation and tier assignment
# ----------------------------------------------------------
@router.post(
    "/{assessment_id}/submit-assessment",
    summary="Submit answers and compute tiered scores",
)
def submit_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    assessment = db.query(models.Assessment).get(assessment_id)
    if not assessment or assessment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Assessment not found")

    scoring_config_version = "v1"  # ✅ must align with B7 defaults

    # ✅ B7: compute + persist student_skill_scores first
    try:
        skill_score_map = compute_and_persist_skill_scores(
            db=db,
            assessment_id=assessment_id,
            student_id=current_user.id,
        )
    except EmptyResponsesError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No responses submitted for this assessment"
        )

    # ✅ B8: sync persisted skill scores → student_keyskill_map (analytics)
    # NOTE: This does NOT change endpoint response; it is internal side-effect.
    sync_skill_scores_to_keyskills(
        db=db,
        assessment_id=assessment_id,
        scoring_config_version=scoring_config_version,
    )

    # ✅ B9: recompute analytics AFTER B8 completes successfully
    # IMPORTANT: B9 expects student_id = students.id (profile id).
    # We currently have current_user.id (users.id). Map safely via students.user_id.
    student_profile = (
        db.query(models.Student)
        .filter(models.Student.user_id == current_user.id)
        .first()
    )
    if student_profile:
        # Internal side-effect only; do NOT change response contract.
        _analytics_result = recompute_student_analytics(
            db=db,
            student_id=student_profile.id,
            scoring_config_version=scoring_config_version,
        )
        
    # If no student_profile exists, we skip analytics recompute safely (no exception).

    # ✅ Option A: Feed assign_tiers with avg_raw (1–5 scale) so existing thresholds work
    scores_for_tiers: Dict[int, float] = {
        int(skill_id): float(data["avg_raw"])
        for skill_id, data in skill_score_map["skills"].items()
    }

    tiers = assign_tiers(scores_for_tiers)

    # 2) Upsert into AssessmentResult (update if exists, else create)
    from datetime import datetime

    existing = (
        db.query(models.AssessmentResult)
        .filter(models.AssessmentResult.assessment_id == assessment_id)
        .first()
    )

    if existing:
        existing.recommended_stream = "Auto"     # TODO: smarter logic later
        existing.recommended_careers = []        # store as JSON list
        existing.skill_tiers = tiers
        existing.generated_at = datetime.utcnow()
        result = existing
    else:
        result = models.AssessmentResult(
            assessment_id=assessment_id,
            recommended_stream="Auto",
            recommended_careers=[],   # JSON list
            skill_tiers=tiers,
        )
        db.add(result)

    db.commit()
    db.refresh(result)

    return {
        "assessment_id": assessment_id,
        "skill_scores": scores_for_tiers,  # keep same response contract shape
        "tiers": tiers,
    }


# ----------------------------------------------------------
# 📤 Fetch assessment info
# ----------------------------------------------------------
@router.get(
    "/{assessment_id}",
    response_model=schemas.AssessmentOut,
    summary="Fetch an assessment",
)
def get_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    assessment = db.query(models.Assessment).get(assessment_id)
    if not assessment or assessment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found"
        )
    return assessment


# ----------------------------------------------------------
# 📈 Fetch computed results (+ tiers)
# ----------------------------------------------------------
@router.get(
    "/{assessment_id}/result",
    response_model=schemas.AssessmentResultOut,
    summary="Fetch the result of an assessment",
)
def get_result(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = (
        db.query(models.AssessmentResult)
        .filter_by(assessment_id=assessment_id)
        .first()
    )
    if not result or result.assessment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not ready"
        )

    # ✅ recommended_careers is JSONB in your model, so keep it as list if present.
    careers = result.recommended_careers or []
    if isinstance(careers, str):
        careers = careers.split(",") if careers else []

    return schemas.AssessmentResultOut(
        assessment_id=result.assessment_id,
        recommended_stream=result.recommended_stream,
        recommended_careers=careers,
        skill_tiers=result.skill_tiers,
        generated_at=result.generated_at,
    )


# ----------------------------------------------------------
# 🧠 Background result generator (Step 5 safe)
# ----------------------------------------------------------
def generate_result(assessment_id: int, student_id: int) -> None:
    db = SessionLocal()
    try:
        existing = db.query(models.AssessmentResult).filter_by(
            assessment_id=assessment_id
        ).first()
        if existing:
            return

        scoring_config_version = "v1"  # ✅ must align with B7 defaults

        # ✅ B7 scoring
        try:
            skill_score_map = compute_and_persist_skill_scores(
                db=db,
                assessment_id=assessment_id,
                student_id=student_id,
            )
        except EmptyResponsesError:
            return

        # ✅ B8: sync persisted skill scores → student_keyskill_map (analytics)
        sync_skill_scores_to_keyskills(
            db=db,
            assessment_id=assessment_id,
            scoring_config_version=scoring_config_version,
        )

        # ✅ B9: recompute analytics AFTER B8 completes successfully (background session)
        # Background arg "student_id" here is users.id. Map to students.id safely.
        student_profile = (
            db.query(models.Student)
            .filter(models.Student.user_id == student_id)
            .first()
        )
        if student_profile:
            _analytics_result = recompute_student_analytics(
                db=db,
                student_id=student_profile.id,
                scoring_config_version=scoring_config_version,
            )
            
        # If no student_profile exists, skip safely.

        # ✅ Option A: use avg_raw (1–5 scale) so assign_tiers thresholds apply correctly
        scores_for_tiers: Dict[int, float] = {
            int(skill_id): float(data["avg_raw"])
            for skill_id, data in skill_score_map["skills"].items()
        }

        tiers = assign_tiers(scores_for_tiers)

        # Save assessment result
        result = models.AssessmentResult(
            assessment_id=assessment_id,
            recommended_stream="Auto",
            recommended_careers=[],
            skill_tiers=tiers,
        )
        db.add(result)
        db.commit()

        # Write tiers → numeric → student_keyskill_map.score (existing behavior retained)
        apply_keyskill_tiers(
            db=db,
            student_id=student_id,
            keyskill_tiers=tiers
        )

    finally:
        db.close()
# ----------------------------------------------------------
# 🌍 Context Profile Capture (CPS) — Append-only (Hybrid Model)
# ----------------------------------------------------------
@router.post(
    "/context-profile",
    response_model=schemas.ContextProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create Context Profile (CPS) for an assessment (immutable)",
)
def create_context_profile(
    payload: schemas.ContextProfileCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Append-only Context Profile capture for Hybrid Model.
    Immutability rule:
    - One ContextProfile per assessment_id.
    Strict validation:
    - assessment_id must exist and belong to current_user.
    """

    # 1) Ensure assessment exists and belongs to the current user
    assessment = db.query(models.Assessment).get(payload.assessment_id)
    if not assessment or assessment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found",
        )
    
    # 1b) Strict version enforcement: payload must match pinned versions
    if payload.assessment_version != assessment.assessment_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="assessment_version mismatch for this assessment session",
        )
    if payload.scoring_config_version != assessment.scoring_config_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="scoring_config_version mismatch for this assessment session",
        )

    # 2) Enforce immutability: only one ContextProfile per assessment
    existing = (
        db.query(models.ContextProfile)
        .filter(models.ContextProfile.assessment_id == payload.assessment_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Context profile already exists for this assessment (immutable)",
        )

    # 3) Compute CPS deterministically (v1)
    cps_score = compute_cps_v1(
        ses_band=payload.ses_band,
        education_board=payload.education_board,
        support_level=payload.support_level,
    )

    # 4) Insert row (version-pinned)
    row = models.ContextProfile(
        assessment_id=payload.assessment_id,
        student_id=payload.student_id,
        assessment_version=assessment.assessment_version,
        scoring_config_version=assessment.scoring_config_version,
        ses_band=payload.ses_band,
        education_board=payload.education_board,
        support_level=payload.support_level,
        resource_access=payload.resource_access,
        cps_score=cps_score,
    )

    db.add(row)
    db.commit()
    db.refresh(row)
    return row