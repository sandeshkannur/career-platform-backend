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
from sqlalchemy.exc import IntegrityError

from app import models, schemas
from app.deps import get_db
from app.auth.auth import get_current_active_user
from sqlalchemy import func
from app.schemas_resume import ActiveAssessmentResponse

# 🧠 Scoring logic for assessments (kept)
from app.utils.scoring import compute_skill_scores, assign_tiers, compute_cps_v1, compute_hsi_v1

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

def _persist_hsi_for_assessment_skill_scores(
    db: Session,
    assessment_id: int,
    scoring_config_version: str,
    assessment_version: str,
    cps_score_used: float,
) -> None:
    

    """
    Persist HSI fields into existing student_skill_scores rows for this assessment/version.

    Safe + additive:
    - Does NOT modify raw_total/question_count/avg_raw/scaled_0_100
    - Only fills hsi_score/cps_score_used/assessment_version
    - Idempotent: re-running overwrites with the same deterministic values
    """
    rows = (
        db.query(models.StudentSkillScore)
        .filter(
            models.StudentSkillScore.assessment_id == assessment_id,
            models.StudentSkillScore.scoring_config_version == scoring_config_version,
        )
        .all()
    )
    
    for row in rows:
        # Use the same scale as tiering currently uses in this file: avg_raw (1–5-ish)
        row.hsi_score = compute_hsi_v1(float(row.avg_raw), float(cps_score_used))
        row.cps_score_used = float(cps_score_used)
        row.assessment_version = assessment_version

    db.commit()
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
# 📝 Submit question responses (append-only, immutable)
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
    try:
        for r in responses:
            resp = models.AssessmentResponse(
                assessment_id=assessment_id,
                question_id=r.question_id,
                answer=r.answer,
            )
            db.add(resp)
            saved.append(resp)

        db.commit()

    except IntegrityError:
        # Uniqueness constraint hit: (assessment_id, question_id) already exists
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Immutable answers: this question_id was already submitted for this assessment.",
        )

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

    scoring_config_version = assessment.scoring_config_version  # pinned, backend authoritative

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

    # ✅ Tiering base (keep exactly as-is for response contract)
    # avg_raw is on your existing 1–5-ish scale, so thresholds in assign_tiers still make sense.
    scores_for_tiers: Dict[int, float] = {
        int(skill_id): float(data["avg_raw"])
        for skill_id, data in skill_score_map["skills"].items()
    }

    # ✅ HSI v1: fetch CPS for this assessment (immutable 1:1); fallback CPS=0 if missing
    context = (
        db.query(models.ContextProfile)
        .filter(models.ContextProfile.assessment_id == assessment_id)
        .first()
    )
    cps_score = float(getattr(context, "cps_score", 0.0) or 0.0)

    

    # ✅ HSI persistence Option A (no response contract change)
    _persist_hsi_for_assessment_skill_scores(
        db=db,
        assessment_id=assessment_id,
        scoring_config_version=scoring_config_version,
        assessment_version=assessment.assessment_version,
        cps_score_used=cps_score,
    )

    # ✅ Apply HSI to the SAME score scale used for tiering (least-breaking approach)
    scores_for_tiers_hsi: Dict[int, float] = {
        skill_id: compute_hsi_v1(raw_score, cps_score)
        for skill_id, raw_score in scores_for_tiers.items()
    }

    # ✅ Tiers now reflect HSI-adjusted values
    tiers = assign_tiers(scores_for_tiers_hsi)

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
        "skill_scores": scores_for_tiers,  # ✅ unchanged response contract (raw)
        "tiers": tiers,                    # ✅ tiers now HSI-based
    }

# ----------------------------------------------------------
# ▶️ Fetch active assessment resume state (Milestone 3)
# ----------------------------------------------------------
@router.get(
    "/active",
    response_model=ActiveAssessmentResponse,
    summary="Fetch the latest active (not completed) assessment resume state",
)
def get_active_assessment(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Deterministic rule (A3):
    - Primary: latest assessment for this user where no assessment_result exists yet
    - Fallback: if none, latest assessment where answered_count < total_questions
    - Allows answered_count = 0 (fresh assessment) to be active
    """

    # Total questions (stable, cheap)
    total_questions = db.query(func.count(models.Question.id)).scalar() or 0

    # Helper to count answered responses for an assessment
    def _answered_count(a_id: int) -> int:
        return (
            db.query(func.count(models.AssessmentResponse.id))
            .filter(models.AssessmentResponse.assessment_id == a_id)
            .scalar()
        ) or 0

    # 1) Primary: latest assessment without a result yet (treat as not completed)
    assessment = (
        db.query(models.Assessment)
        .outerjoin(
            models.AssessmentResult,
            models.AssessmentResult.assessment_id == models.Assessment.id,
        )
        .filter(models.Assessment.user_id == current_user.id)
        .filter(models.AssessmentResult.id.is_(None))
        .order_by(models.Assessment.id.desc())
        .first()
    )

    # 2) Fallback: if none, pick the latest assessment where answered_count < total_questions
    if not assessment and total_questions > 0:
        latest = (
            db.query(models.Assessment)
            .filter(models.Assessment.user_id == current_user.id)
            .order_by(models.Assessment.id.desc())
            .limit(10)  # deterministic window: newest 10
            .all()
        )
        for a in latest:
            if _answered_count(a.id) < total_questions:
                assessment = a
                break

    if not assessment:
        return ActiveAssessmentResponse(active=False)

    # 3) Count answered (0 is allowed now)
    answered_count = _answered_count(assessment.id)

    # 4) Last answered question_id (only if any answered)
    last_qid = None
    if answered_count > 0:
        last_qid = (
            db.query(models.AssessmentResponse.question_id)
            .filter(models.AssessmentResponse.assessment_id == assessment.id)
            .order_by(models.AssessmentResponse.id.desc())
            .limit(1)
            .scalar()
        )
    # 5) Determine next_question_id deterministically (by Question.id ascending)
    next_qid = None

    if total_questions > 0:
        if answered_count == 0:
            # First question in deterministic order
            next_qid = db.query(models.Question.id).order_by(models.Question.id.asc()).limit(1).scalar()
        else:
            # Next question after the last answered one
            # Note: question_id in responses may be stored as string; coerce safely
            try:
                last_qid_int = int(last_qid) if last_qid is not None else None
            except (TypeError, ValueError):
                last_qid_int = None

            if last_qid_int is not None:
                next_qid = (
                    db.query(models.Question.id)
                    .filter(models.Question.id > last_qid_int)
                    .order_by(models.Question.id.asc())
                    .limit(1)
                    .scalar()
                )

    return ActiveAssessmentResponse(
        active=True,
        assessment_id=assessment.id,
        assessment_version=getattr(assessment, "assessment_version", None),
        scoring_config_version=getattr(assessment, "scoring_config_version", None),
        answered_count=int(answered_count),
        last_answered_question_id=str(last_qid) if last_qid is not None else None,
        next_question_id=str(next_qid) if next_qid is not None else None,
        total_questions=int(total_questions),
    )

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

        assessment = db.query(models.Assessment).get(assessment_id)
        if not assessment:
            return

        scoring_config_version = assessment.scoring_config_version
        assessment_version_used = assessment.assessment_version

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

        # ✅ HSI v1: fetch CPS for this assessment; fallback CPS=0 if missing
        context = (
            db.query(models.ContextProfile)
            .filter(models.ContextProfile.assessment_id == assessment_id)
            .first()
        )
        cps_score = float(getattr(context, "cps_score", 0.0) or 0.0)

        # ✅ Persist HSI into student_skill_scores (Option A) - background safe
        _persist_hsi_for_assessment_skill_scores(
            db=db,
            assessment_id=assessment_id,
            scoring_config_version=scoring_config_version,
            assessment_version=assessment_version_used,
            cps_score_used=cps_score,
        )

        # ✅ Tiers reflect HSI-adjusted values (consistent with submit_assessment)
        scores_for_tiers_hsi: Dict[int, float] = {
            skill_id: compute_hsi_v1(raw_score, cps_score)
            for skill_id, raw_score in scores_for_tiers.items()
        }
        tiers = assign_tiers(scores_for_tiers_hsi)

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