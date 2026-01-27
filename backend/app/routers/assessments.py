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
from sqlalchemy import and_

from app import models, schemas
from app.deps import get_db
from app.auth.auth import get_current_active_user
from sqlalchemy import func
from sqlalchemy import text
from app.schemas_resume import ActiveAssessmentResponse
from app.schemas_response_submit import SubmitResponseOut

# Scoring logic for assessments (kept)
from app.utils.scoring import compute_skill_scores, assign_tiers, compute_cps_v1, compute_hsi_v1

# Existing
from app.services.tier_mapping import apply_keyskill_tiers

# B7 scoring service (NEW)
from app.services.assessment_scoring_service import (
    compute_and_persist_skill_scores,
    EmptyResponsesError,
)

# B8 keyskill sync service (NEW)
from app.services.keyskill_sync_service import sync_skill_scores_to_keyskills

# B9 analytics orchestrator service (NEW - internal)
from app.services.analytics_orchestrator_service import recompute_student_analytics

# Step 5 fix: background task must create its own session
from app.database import SessionLocal


router = APIRouter(
    tags=["Assessments"],
)

def _sample_75_questions_v1(db: Session) -> List[Dict]:
    """
    Returns 75 questions (3 per AQ) for assessment_version='v1'.

    Shape:
      [{"question_id": int, "question_code": str, "aq_code": str}, ...]
    """
    rows = db.execute(
        text(
            """
            WITH pool AS (
              SELECT
                q.id AS question_id,
                q.question_code,
                f.aq_code,
                ROW_NUMBER() OVER (PARTITION BY f.aq_code ORDER BY RANDOM()) AS rn
              FROM questions q
              JOIN question_facet_tags_v t
                ON t.assessment_version=q.assessment_version
               AND t.question_code=q.question_code
              JOIN aq_facets_v f
                ON f.assessment_version=q.assessment_version
               AND f.facet_code=t.facet_code
              WHERE q.assessment_version='v1'
            ),
            pick AS (
              SELECT * FROM pool WHERE rn <= 3
            )
            SELECT question_id, question_code, aq_code
            FROM pick
            ORDER BY aq_code, question_id;
            """
        )
    ).fetchall()

    picked = [{"question_id": int(r[0]), "question_code": str(r[1]), "aq_code": str(r[2])} for r in rows]

    if len(picked) != 75:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sampler failed: expected 75 questions, got {len(picked)}",
        )

    return picked


def _persist_assessment_questions(
    db: Session,
    assessment_id: int,
    assessment_version: str,
    picked: List[Dict],
) -> None:
    """
    Insert rows into assessment_questions.
    Idempotent: if rows already exist for this assessment, do nothing.
    """
    exists = (
        db.query(models.AssessmentQuestion.id)
        .filter(models.AssessmentQuestion.assessment_id == assessment_id)
        .first()
    )
    if exists:
        return

    for item in picked:
        db.add(
            models.AssessmentQuestion(
                assessment_id=assessment_id,
                question_id=item["question_id"],
                assessment_version=assessment_version,
                question_code=item["question_code"],
            )
        )

    db.commit()

def _ensure_context_profile_for_assessment(
    db: Session,
    assessment: models.Assessment,
    current_user_id: int,
) -> models.ContextProfile:
    """
    Guarantee: exactly one ContextProfile per assessment attempt.
    - Idempotent: returns existing row if present.
    - Creates a placeholder row with safe defaults if missing.
    - Backend-authoritative baseline for offline/retry-safe scoring.
    """

    existing = (
        db.query(models.ContextProfile)
        .filter(models.ContextProfile.assessment_id == assessment.id)
        .first()
    )
    if existing:
        return existing

    # Resolve student profile (students.id) from current_user (users.id)
    student_profile = (
        db.query(models.Student)
        .filter(models.Student.user_id == current_user_id)
        .first()
    )
    if not student_profile:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student profile not found for this user. Create student profile before starting/submitting assessment.",
        )

    # Safe placeholders (non-intimidating UX; user can confirm/update later)
    ses_band = "unknown"
    education_board = "unknown"
    support_level = "unknown"
    resource_access = "unknown"

    # Compute CPS deterministically (your compute_cps_v1 has safe defaults)
    cps_score = compute_cps_v1(
        ses_band=ses_band,
        education_board=education_board,
        support_level=support_level,
        resource_access=resource_access,
    )

    row = models.ContextProfile(
        assessment_id=assessment.id,
        student_id=student_profile.id,
        assessment_version=assessment.assessment_version,
        scoring_config_version=assessment.scoring_config_version,
        ses_band=ses_band,
        education_board=education_board,
        support_level=support_level,
        resource_access=resource_access,
        cps_score=float(cps_score),
    )

    db.add(row)
    db.commit()
    db.refresh(row)
    return row

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


def _load_skill_score_map_from_db(
    db: Session,
    assessment_id: int,
    scoring_config_version: str,
) -> Dict:
    
    """
    Build the same minimal shape used by submit_assessment from already-persisted rows.
    This is used to make /submit-assessment idempotent if scores already exist.
    """
    rows = (
        db.query(models.StudentSkillScore)
        .filter(
            models.StudentSkillScore.assessment_id == assessment_id,
            models.StudentSkillScore.scoring_config_version == scoring_config_version,
        )
        .all()
    )

    skills = {}
    for r in rows:
        # keys are strings to match existing service output shape
        skills[str(r.skill_id)] = {
            "avg_raw": float(r.avg_raw),
            "raw_total": float(getattr(r, "raw_total", 0.0) or 0.0),
            "question_count": int(getattr(r, "question_count", 0) or 0),
            "scaled_0_100": float(getattr(r, "scaled_0_100", 0.0) or 0.0),
        }

    return {"skills": skills}
def _ensure_context_profile_for_assessment(
    db: Session,
    assessment: models.Assessment,
    current_user_id: int,
) -> models.ContextProfile:
    """
    World-class baseline:
    - ContextProfile MUST exist for every assessment attempt.
    - If missing, create a placeholder snapshot with 'unknown' fields.
    - This keeps scoring deterministic + enables UI to later prompt "Confirm/Update context".
    - Idempotent: if already exists, return it.
    """
    existing = (
        db.query(models.ContextProfile)
        .filter(models.ContextProfile.assessment_id == assessment.id)
        .first()
    )
    if existing:
        return existing

    # Map users.id -> students.id (profile id)
    student_profile = (
        db.query(models.Student)
        .filter(models.Student.user_id == current_user_id)
        .first()
    )
    if not student_profile:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student profile not found for this user. Create student profile before submitting assessment.",
        )

    # Placeholder values: intentionally neutral + safe for low-friction flows
    ses_band = "unknown"
    education_board = "unknown"
    support_level = "unknown"
    resource_access = "unknown"

    # CPS will compute deterministically; if your compute_cps_v1 doesn't handle 'unknown',
    # you can safely fallback to 0.0
    try:
        cps_score = compute_cps_v1(
            ses_band=ses_band,
            education_board=education_board,
            support_level=support_level,
            resource_access=resource_access,
        )
    except Exception:
        cps_score = 0.0

    row = models.ContextProfile(
        assessment_id=assessment.id,
        student_id=student_profile.id,
        assessment_version=assessment.assessment_version,
        scoring_config_version=assessment.scoring_config_version,
        ses_band=ses_band,
        education_board=education_board,
        support_level=support_level,
        resource_access=resource_access,
        cps_score=float(cps_score),
    )

    db.add(row)
    db.commit()
    db.refresh(row)
    return row
# ----------------------------------------------------------
# Start a new assessment
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
    # 1) Create assessment shell
    assessment = models.Assessment(
        user_id=current_user.id,
        assessment_version="v1",
        scoring_config_version="v1",
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    # 2) Ensure ContextProfile exists (existing behavior)
    _ensure_context_profile_for_assessment(
        db=db,
        assessment=assessment,
        current_user_id=current_user.id,
    )

    # 3) Pick + persist 75 AQ-balanced questions
    picked = _sample_75_questions_v1(db=db)
    _persist_assessment_questions(
        db=db,
        assessment_id=assessment.id,
        assessment_version=assessment.assessment_version,
        picked=picked,
    )

    return assessment


# ----------------------------------------------------------
#  Submit question responses (append-only, immutable)
# ----------------------------------------------------------
@router.post(
    "/{assessment_id}/responses",
    response_model=SubmitResponseOut,
    summary="Submit response(s) (immutable) and return resume pointer",
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

    if not responses or len(responses) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No responses provided"
        )
    # ------------------------------------------------------
    # M4-A2: Pre-fetch existing question_ids for this assessment
    # Allows partial offline replay batches to succeed safely
    # ------------------------------------------------------
    existing_qids = {
        row[0]
        for row in db.query(models.AssessmentResponse.question_id)
        .filter(models.AssessmentResponse.assessment_id == assessment_id)
        .all()
    }
    try:
        for r in responses:
            # 1) If idempotency_key was already used for this assessment, treat as replay-success
            if r.idempotency_key:
                existing = (
                    db.query(models.AssessmentResponse.id)
                    .filter(
                        and_(
                            models.AssessmentResponse.assessment_id == assessment_id,
                            models.AssessmentResponse.idempotency_key == r.idempotency_key,
                        )
                    )
                    .first()
                )
                if existing:
                    # Replay: do NOT insert; continue to next response in the batch
                    continue
                # ✅ Validate question_code if provided (prevents mismatched IDs/codes from corrupting analytics)
            if getattr(r, "question_code", None):
                try:
                    qid_int = int(str(r.question_id).strip())
                except (TypeError, ValueError):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"question_id must be integer-like when question_code is provided (got '{r.question_id}')",
                    )

                q = db.query(models.Question).filter(models.Question.id == qid_int).first()
                if not q:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Question not found: id={qid_int}",
                    )

                expected_code = (q.question_code or "").strip()
                provided_code = (r.question_code or "").strip()

                if expected_code != provided_code:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"question_code mismatch for question_id={qid_int}: got '{provided_code}', expected '{expected_code}'",
                    )

            # 2) Skip if this question was already answered (offline replay batch safety)
            if r.question_id in existing_qids:
                continue

            resp = models.AssessmentResponse(
                assessment_id=assessment_id,
                question_id=r.question_id,
                answer=r.answer,
                idempotency_key=r.idempotency_key,
            )
            db.add(resp)

        db.commit()

    except IntegrityError:
        db.rollback()

        # Race-safe idempotency: if conflict happened but keys exist, check if it's an idempotency replay
        if any(r.idempotency_key for r in responses):
            replay_found = (
                db.query(models.AssessmentResponse.id)
                .filter(models.AssessmentResponse.assessment_id == assessment_id)
                .filter(models.AssessmentResponse.idempotency_key.in_([r.idempotency_key for r in responses if r.idempotency_key]))
                .first()
            )
            if replay_found:
                # Treat as idempotent success (resume pointer returned below)
                pass
            else:
                # Not an idempotency replay → preserve existing 409 behavior
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Immutable answers: this question_id was already submitted for this assessment.",
                )
        else:
            # No idempotency keys provided → preserve existing 409 behavior
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Immutable answers: this question_id was already submitted for this assessment.",
            )

    # M4-A4: Avoid duplicate background jobs on offline replay
    result_exists = (
    db.query(models.AssessmentResult.id)
    .filter(models.AssessmentResult.assessment_id == assessment_id)
    .first()
    )
    if not result_exists:
        background_tasks.add_task(generate_result, assessment_id, current_user.id)

    # ---- Resume pointer (deterministic, 75-question aware) ----
    persisted_ids = [
        r[0]
        for r in db.query(models.AssessmentQuestion.question_id)
        .filter(models.AssessmentQuestion.assessment_id == assessment_id)
        .order_by(models.AssessmentQuestion.id.asc())
        .all()
    ]

    # If persisted set exists, it is authoritative (75 questions)
    if persisted_ids:
        total_questions = len(persisted_ids)
    else:
        # Legacy fallback for old/test assessments (pre-persist)
        total_questions = db.query(func.count(models.Question.id)).scalar() or 0

    answered_count = (
        db.query(func.count(models.AssessmentResponse.id))
        .filter(models.AssessmentResponse.assessment_id == assessment_id)
        .scalar()
    ) or 0

    last_qid = (
        db.query(models.AssessmentResponse.question_id)
        .filter(models.AssessmentResponse.assessment_id == assessment_id)
        .order_by(models.AssessmentResponse.id.desc())
        .limit(1)
        .scalar()
    )

    next_qid = None

    if total_questions > 0:
        if persisted_ids:
            # Next question comes from the persisted list order
            if answered_count == 0:
                next_qid = persisted_ids[0]
            else:
                try:
                    last_qid_int = int(last_qid) if last_qid is not None else None
                except (TypeError, ValueError):
                    last_qid_int = None

                if last_qid_int is not None and last_qid_int in persisted_ids:
                    idx = persisted_ids.index(last_qid_int)
                    next_qid = persisted_ids[idx + 1] if (idx + 1) < len(persisted_ids) else None
                else:
                    # Safe fallback: start at the first question in the set
                    next_qid = persisted_ids[0]
        else:
            # Legacy fallback: next question by global Question.id
            try:
                last_qid_int = int(last_qid) if last_qid is not None else None
            except (TypeError, ValueError):
                last_qid_int = None

            if last_qid_int is None and answered_count == 0:
                next_qid = db.query(models.Question.id).order_by(models.Question.id.asc()).limit(1).scalar()
            elif last_qid_int is not None:
                next_qid = (
                    db.query(models.Question.id)
                    .filter(models.Question.id > last_qid_int)
                    .order_by(models.Question.id.asc())
                    .limit(1)
                    .scalar()
                )

    is_complete = (next_qid is None) and (answered_count >= total_questions)       

    # For the response payload, report the last question_id from THIS request (string)
    last_submitted_qid = responses[-1].question_id

    return SubmitResponseOut(
        success=True,
        assessment_id=assessment_id,
        question_id=str(last_submitted_qid),
        answered_count=int(answered_count),
        last_answered_question_id=str(last_qid) if last_qid is not None else None,
        next_question_id=str(next_qid) if next_qid is not None else None,
        total_questions=int(total_questions),
        is_complete=is_complete,
    )

# ----------------------------------------------------------
#  Manual trigger for score computation and tier assignment
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
    _ensure_context_profile_for_assessment(
    db=db,
    assessment=assessment,
    current_user_id=current_user.id,
    )

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
    except IntegrityError:
        # Idempotency: scores likely already persisted for this assessment+config.
        db.rollback()
        skill_score_map = _load_skill_score_map_from_db(
            db=db,
            assessment_id=assessment_id,
            scoring_config_version=scoring_config_version,
        )
        if not skill_score_map.get("skills"):
            # If still empty, surface a deterministic server error (not a crash loop).
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Skill scores already exist but could not be loaded"
            )

    #  B8: sync persisted skill scores → student_keyskill_map (analytics)
    # NOTE: This does NOT change endpoint response; it is internal side-effect.
    sync_skill_scores_to_keyskills(
        db=db,
        assessment_id=assessment_id,
        scoring_config_version=scoring_config_version,
    )

    #  B9: recompute analytics AFTER B8 completes successfully
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

    #  Tiering base (keep exactly as-is for response contract)
    # avg_raw is on your existing 1–5-ish scale, so thresholds in assign_tiers still make sense.
    scores_for_tiers: Dict[int, float] = {
        int(skill_id): float(data["avg_raw"])
        for skill_id, data in skill_score_map["skills"].items()
    }

    # HSI v1: fetch CPS for this assessment (immutable 1:1); fallback CPS=0 if missing
    context = (
                db.query(models.ContextProfile)
                .filter(models.ContextProfile.assessment_id == assessment_id)
                .first()
    )
    cps_score = float(getattr(context, "cps_score", 0.0) or 0.0)

    

    # HSI persistence Option A (no response contract change)
    _persist_hsi_for_assessment_skill_scores(
        db=db,
        assessment_id=assessment_id,
        scoring_config_version=scoring_config_version,
        assessment_version=assessment.assessment_version,
        cps_score_used=cps_score,
    )

    #  Apply HSI to the SAME score scale used for tiering (least-breaking approach)
    scores_for_tiers_hsi: Dict[int, float] = {
        skill_id: compute_hsi_v1(raw_score, cps_score)
        for skill_id, raw_score in scores_for_tiers.items()
    }

    #  Tiers now reflect HSI-adjusted values
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
        "skill_scores": scores_for_tiers,  #  unchanged response contract (raw)
        "tiers": tiers,                    #  tiers now HSI-based
    }

# ----------------------------------------------------------
#  Fetch active assessment resume state (Milestone 3)
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

    # Total questions (75-question aware)
    persisted_ids = [
        r[0]
        for r in db.query(models.AssessmentQuestion.question_id)
        .filter(models.AssessmentQuestion.assessment_id == assessment.id)
        .order_by(models.AssessmentQuestion.id.asc())
        .all()
    ]

    if persisted_ids:
        total_questions = len(persisted_ids)
    else:
        # Legacy fallback for old/test assessments (pre-persist)
        total_questions = db.query(func.count(models.Question.id)).scalar() or 0

    # Helper to count answered responses for an assessment
    def _answered_count(a_id: int) -> int:
        return (
            db.query(func.count(models.AssessmentResponse.id))
            .filter(models.AssessmentResponse.assessment_id == a_id)
            .scalar()
        ) or 0

    answered_count = _answered_count(assessment.id)

    last_qid = (
        db.query(models.AssessmentResponse.question_id)
        .filter(models.AssessmentResponse.assessment_id == assessment.id)
        .order_by(models.AssessmentResponse.id.desc())
        .limit(1)
        .scalar()
    )

    # Determine next_question_id deterministically
    next_qid = None

    if total_questions > 0:
        if persisted_ids:
            if answered_count == 0:
                next_qid = persisted_ids[0]
            else:
                try:
                    last_qid_int = int(last_qid) if last_qid is not None else None
                except (TypeError, ValueError):
                    last_qid_int = None

                if last_qid_int is not None and last_qid_int in persisted_ids:
                    idx = persisted_ids.index(last_qid_int)
                    next_qid = persisted_ids[idx + 1] if (idx + 1) < len(persisted_ids) else None
                else:
                    next_qid = persisted_ids[0]
        else:
            # Legacy fallback: global Question.id order
            if answered_count == 0:
                next_qid = db.query(models.Question.id).order_by(models.Question.id.asc()).limit(1).scalar()
            else:
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

    is_complete = (next_qid is None) and (answered_count >= total_questions)           



    return ActiveAssessmentResponse(
        active=True,
        assessment_id=assessment.id,
        assessment_version=getattr(assessment, "assessment_version", None),
        scoring_config_version=getattr(assessment, "scoring_config_version", None),
        answered_count=int(answered_count),
        last_answered_question_id=str(last_qid) if last_qid is not None else None,
        next_question_id=str(next_qid) if next_qid is not None else None,
        total_questions=int(total_questions),
        is_complete=is_complete,
    )

# ----------------------------------------------------------
#  Fetch assessment info
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
#  Fetch computed results (+ tiers)
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

    #  recommended_careers is JSONB in your model, so keep it as list if present.
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
#  Background result generator (Step 5 safe)
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

        #  B7 scoring
        try:
            skill_score_map = compute_and_persist_skill_scores(
                db=db,
                assessment_id=assessment_id,
                student_id=student_id,
            )
        except EmptyResponsesError:
            return
        except IntegrityError:
            # Idempotency/race: scores already persisted (e.g. submit_assessment ran first).
            db.rollback()
            skill_score_map = _load_skill_score_map_from_db(
                db=db,
                assessment_id=assessment_id,
                scoring_config_version=scoring_config_version,
            )
            if not skill_score_map.get("skills"):
                return

        #  B8: sync persisted skill scores → student_keyskill_map (analytics)
        sync_skill_scores_to_keyskills(
            db=db,
            assessment_id=assessment_id,
            scoring_config_version=scoring_config_version,
        )

        #  B9: recompute analytics AFTER B8 completes successfully (background session)
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

        #  Option A: use avg_raw (1–5 scale) so assign_tiers thresholds apply correctly
        scores_for_tiers: Dict[int, float] = {
            int(skill_id): float(data["avg_raw"])
            for skill_id, data in skill_score_map["skills"].items()
        }

        #  HSI v1: fetch CPS for this assessment; fallback CPS=0 if missing
        context = _ensure_context_profile_for_assessment(
            db=db,
            assessment=assessment,
            current_user_id=student_id,  # NOTE: in generate_result this arg is users.id
        )
        cps_score = float(getattr(context, "cps_score", 0.0) or 0.0)

        #  Persist HSI into student_skill_scores (Option A) - background safe
        _persist_hsi_for_assessment_skill_scores(
            db=db,
            assessment_id=assessment_id,
            scoring_config_version=scoring_config_version,
            assessment_version=assessment_version_used,
            cps_score_used=cps_score,
        )

        #  Tiers reflect HSI-adjusted values (consistent with submit_assessment)
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
#  Context Profile Capture (CPS) — Append-only (Hybrid Model)
# ----------------------------------------------------------
@router.post(
    "/context-profile",
    response_model=schemas.ContextProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create Context Profile (CPS) for an assessment (immutable)",
)

# ----------------------------------------------------------
#  Context Profile Update (CPS) — Updatable fields
# ----------------------------------------------------------
@router.put(
    "/{assessment_id}/context-profile",
    response_model=schemas.ContextProfileOut,
    summary="Update Context Profile (CPS) for an assessment (recommended for UI)",
)
def update_context_profile(
    assessment_id: int,
    payload: schemas.ContextProfileUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    World-class behaviour:
    - ContextProfile exists 1:1 per assessment attempt (created automatically).
    - UI can update 'unknown' fields later without creating new rows.
    - Recomputes cps_score after updates.
    - Strict ownership: assessment must belong to current_user.
    """

    # 1) Validate assessment belongs to current user
    assessment = db.query(models.Assessment).get(assessment_id)
    if not assessment or assessment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # 2) Fetch existing context row (should exist because of ensure-on-create)
    row = (
        db.query(models.ContextProfile)
        .filter(models.ContextProfile.assessment_id == assessment_id)
        .first()
    )

    # If missing for any legacy reason, create a placeholder deterministically
    if not row:
        row = _ensure_context_profile_for_assessment(
            db=db,
            assessment=assessment,
            current_user_id=current_user.id,
        )

    # 3) Apply partial updates (only fields provided)
    if payload.ses_band is not None:
        row.ses_band = payload.ses_band
    if payload.education_board is not None:
        row.education_board = payload.education_board
    if payload.support_level is not None:
        row.support_level = payload.support_level
    if payload.resource_access is not None:
        row.resource_access = payload.resource_access

    # 4) Recompute CPS score from the updated fields
    try:
        row.cps_score = int(
            compute_cps_v1(
                ses_band=payload.ses_band,
                education_board=payload.education_board,
                support_level=payload.support_level,
                resource_access=payload.resource_access,
            )
        )
    except Exception:
        # Keep deterministic fallback
        row.cps_score = 0

    db.commit()
    db.refresh(row)
    return row
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
    # Resolve student profile (students.id) from current_user (users.id)
    student_profile = (
        db.query(models.Student)
        .filter(models.Student.user_id == current_user.id)
        .first()
    )
    if not student_profile:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student profile not found for this user. Create student profile before submitting context profile.",
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
        # Idempotent replay: return the existing immutable record
        return existing

    # 3) Compute CPS deterministically (v1)
    cps_score = compute_cps_v1(
        ses_band=payload.ses_band,
        education_board=payload.education_board,
        support_level=payload.support_level,
    )

    # 4) Insert row (version-pinned)
    row = models.ContextProfile(
        assessment_id=payload.assessment_id,
        student_id=student_profile.id,
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