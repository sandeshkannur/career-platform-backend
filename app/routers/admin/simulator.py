"""
Admin assessment simulator — generate synthetic student assessments
at full pipeline fidelity.

  POST /v1/admin/simulate-assessment   — single student simulation
  POST /v1/admin/simulate-batch        — bulk simulation with optional auto-creation

Both endpoints:
  - Use the EXACT same scoring code path as real students
  - Write to production tables (assessments, assessment_responses, etc.)
  - Require admin auth
  - Log to admin_audit_trail (action="simulate", entity_type="assessment")

Auto-created students always use the @test.mapyourcareer.in domain so
they cannot collide with real beta testers.
"""
from __future__ import annotations

import logging
import random
import time
import uuid
from collections import Counter
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.auth import authenticate_user, get_password_hash, require_role, get_current_active_user
from app.deps import get_db
from app.models import (
    Assessment, AssessmentQuestion, AssessmentResult, ContextProfile,
    InterestInventoryResponse, Student, User,
)
from app.routers.admin.audit_trail import log_audit
from app.routers.assessments import (
    create_assessment,
    submit_assessment,
    submit_responses,
    _ensure_context_profile_for_assessment,
)
from app.routers.interest_inventory import (
    _compute_cluster_boosts,
    INVENTORY_VERSION,
)
from app.services.career_engine import compute_careers_for_student
from app.utils.scoring import compute_cps_v1

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Persona AQ range tables
# Format: {group_key: [min, max]}  — values are inclusive integers 1-5
# ---------------------------------------------------------------------------

PERSONA_RANGES: Dict[str, Dict[str, List[int]]] = {
    # === COGNITIVE-DOMINANT ===

    "analytical_thinker": {
        # Pure cognition peak. Weak emotional/social.
        # Expected: Data Scientist, Physicist, Mathematician, Statistician
        "aq_01_05": [5, 5], "aq_06_09": [5, 5], "aq_10_14": [3, 4],
        "aq_15_18": [2, 3], "aq_19_22": [1, 2], "aq_23_25": [2, 3],
    },
    "systematic_builder": {
        # Cognitive + Behavioral peak. Wants to design/build.
        # Expected: Mechanical Engineer, Architect, Civil Engineer, Manufacturing Engineer
        "aq_01_05": [4, 5], "aq_06_09": [4, 5], "aq_10_14": [5, 5],
        "aq_15_18": [4, 5], "aq_19_22": [2, 3], "aq_23_25": [2, 3],
    },
    "investigative_researcher": {
        # Curiosity + Persistence peak. Low social.
        # Expected: Researcher, Epidemiologist, Environmental Scientist, Forensic Pathologist
        "aq_01_05": [5, 5], "aq_06_09": [4, 5], "aq_10_14": [3, 4],
        "aq_15_18": [4, 5], "aq_19_22": [2, 3], "aq_23_25": [1, 2],
    },

    # === BEHAVIORAL-DOMINANT ===

    "strategic_leader": {
        # Drive + Communication peak. Moderate everything else.
        # Expected: CEO, General Manager, Management Consultant, Military Officer
        "aq_01_05": [3, 4], "aq_06_09": [3, 4], "aq_10_14": [3, 4],
        "aq_15_18": [5, 5], "aq_19_22": [3, 4], "aq_23_25": [5, 5],
    },
    "organized_executor": {
        # Work + Discipline peak. Low creativity.
        # Expected: Accountant, Auditor, Quality Control Inspector, Logistics Manager
        "aq_01_05": [2, 3], "aq_06_09": [3, 4], "aq_10_14": [4, 5],
        "aq_15_18": [5, 5], "aq_19_22": [3, 4], "aq_23_25": [3, 4],
    },
    "hands_on_maker": {
        # Experimentation + Precision peak. Low cognitive/emotional.
        # Expected: Electrician, Carpenter, Welder, CNC Programmer, Chef
        "aq_01_05": [2, 3], "aq_06_09": [2, 3], "aq_10_14": [5, 5],
        "aq_15_18": [4, 5], "aq_19_22": [2, 3], "aq_23_25": [2, 3],
    },

    # === EMOTIONAL-DOMINANT ===

    "empathetic_healer": {
        # Emotional + Social peak. Moderate cognitive.
        # Expected: Psychologist, Counselor, Social Worker, Nurse, Therapist
        "aq_01_05": [3, 4], "aq_06_09": [2, 3], "aq_10_14": [3, 4],
        "aq_15_18": [3, 4], "aq_19_22": [5, 5], "aq_23_25": [5, 5],
    },
    "creative_visionary": {
        # Emotional + Idea Generation peak. Low discipline.
        # Expected: Art Director, Photographer, Graphic Designer, Fashion Designer, Actor
        "aq_01_05": [3, 4], "aq_06_09": [2, 3], "aq_10_14": [2, 3],
        "aq_15_18": [2, 3], "aq_19_22": [5, 5], "aq_23_25": [4, 5],
    },
    "patient_educator": {
        # Communication + Emotional + moderate cognitive.
        # Expected: Teacher, Corporate Trainer, Career Counselor, Dean
        "aq_01_05": [3, 4], "aq_06_09": [3, 4], "aq_10_14": [3, 4],
        "aq_15_18": [3, 4], "aq_19_22": [4, 5], "aq_23_25": [5, 5],
    },

    # === CROSS-DOMAIN ===

    "tech_creative_hybrid": {
        # Cognitive + Emotional peak. Bridge between tech and art.
        # Expected: UX/UI Designer, Game Developer, Web Developer, Digital Marketer
        "aq_01_05": [4, 5], "aq_06_09": [4, 5], "aq_10_14": [3, 4],
        "aq_15_18": [2, 3], "aq_19_22": [4, 5], "aq_23_25": [3, 4],
    },
    "science_people_bridge": {
        # Cognitive + Emotional + Social. Science meets caring.
        # Expected: Epidemiologist, Biomedical Engineer, Speech Pathologist, Psychiatrist
        "aq_01_05": [4, 5], "aq_06_09": [3, 4], "aq_10_14": [3, 4],
        "aq_15_18": [3, 4], "aq_19_22": [4, 5], "aq_23_25": [4, 5],
    },
    "entrepreneurial_connector": {
        # Social + Drive peak. Moderate everything else.
        # Expected: Real Estate Agent, Event Planner, Fundraising Manager, Life Coach
        "aq_01_05": [3, 4], "aq_06_09": [3, 4], "aq_10_14": [3, 4],
        "aq_15_18": [4, 5], "aq_19_22": [3, 4], "aq_23_25": [5, 5],
    },

    # === CONTROL PERSONAS ===

    "balanced_allrounder": {
        # Flat moderate. Tests multi-domain and gateway careers.
        # Expected: General Manager, Hotel Manager, Police Officer + entry-level
        "aq_01_05": [3, 4], "aq_06_09": [3, 4], "aq_10_14": [3, 4],
        "aq_15_18": [3, 4], "aq_19_22": [3, 4], "aq_23_25": [3, 4],
    },
    "explorer_undecided": {
        # Wide inconsistent range. Tests gateway careers.
        # Expected: Entry-level across multiple clusters
        "aq_01_05": [2, 4], "aq_06_09": [2, 4], "aq_10_14": [2, 4],
        "aq_15_18": [2, 4], "aq_19_22": [2, 4], "aq_23_25": [2, 4],
    },
    "random_stress_test": {
        # Full range. Edge case testing.
        "aq_01_05": [1, 5], "aq_06_09": [1, 5], "aq_10_14": [1, 5],
        "aq_15_18": [1, 5], "aq_19_22": [1, 5], "aq_23_25": [1, 5],
    },
    "low_engagement": {
        # Floor test. Student not trying.
        "aq_01_05": [1, 2], "aq_06_09": [1, 2], "aq_10_14": [1, 2],
        "aq_15_18": [1, 2], "aq_19_22": [1, 2], "aq_23_25": [1, 2],
    },
}

# Backward-compatibility aliases — old 7-persona names map to new equivalents
PERSONA_ALIASES: Dict[str, str] = {
    "stem_explorer":     "analytical_thinker",
    "creative_artist":   "creative_visionary",
    "business_leader":   "strategic_leader",
    "healthcare_helper": "empathetic_healer",
    "balanced":          "balanced_allrounder",
    "random":            "random_stress_test",
    "low_confidence":    "low_engagement",
}

MIXED_CYCLE = [
    "analytical_thinker", "systematic_builder", "investigative_researcher",
    "strategic_leader", "organized_executor", "hands_on_maker",
    "empathetic_healer", "creative_visionary", "patient_educator",
    "tech_creative_hybrid", "science_people_bridge", "entrepreneurial_connector",
    "balanced_allrounder", "explorer_undecided", "random_stress_test", "low_engagement",
]

VALID_PERSONAS = set(PERSONA_RANGES.keys())

# Default context profile values (used when context=null in payload)
DEFAULT_CONTEXT = {
    "education_board": "cbse",
    "ses_band": "some",
    "support_level": "medium",
    "resource_access": "moderate",
}


# ---------------------------------------------------------------------------
# AQ range helpers
# ---------------------------------------------------------------------------

def _extract_aq_num(question_code: str) -> Optional[int]:
    """
    Parse AQ number from question_code like "AQ01_F1_Q001" → 1.
    Returns None if the code is malformed.
    """
    try:
        if question_code.upper().startswith("AQ"):
            return int(question_code[2:4])
    except (ValueError, IndexError):
        pass
    return None


def _aq_num_to_group(aq_num: int) -> str:
    """Map an AQ number (1-25) to its range-group key."""
    if 1 <= aq_num <= 5:
        return "aq_01_05"
    if 6 <= aq_num <= 9:
        return "aq_06_09"
    if 10 <= aq_num <= 14:
        return "aq_10_14"
    if 15 <= aq_num <= 18:
        return "aq_15_18"
    if 19 <= aq_num <= 22:
        return "aq_19_22"
    # 23-25 (and any unexpected value)
    return "aq_23_25"


def _get_range(
    mode: str,
    persona: Optional[str],
    custom_aq_ranges: Optional[Dict[str, List[int]]],
    group: str,
) -> tuple[int, int]:
    """
    Return (min_val, max_val) for a given AQ group.
    Falls back to [3, 4] (balanced) on any misconfiguration.
    """
    if mode == "custom" and custom_aq_ranges and group in custom_aq_ranges:
        r = custom_aq_ranges[group]
        lo = max(1, min(5, int(r[0])))
        hi = max(1, min(5, int(r[1])))
        return (lo, hi) if lo <= hi else (hi, lo)

    if persona and persona in PERSONA_RANGES:
        r = PERSONA_RANGES[persona].get(group, [3, 4])
        return (r[0], r[1])

    return (3, 4)  # balanced fallback


# ---------------------------------------------------------------------------
# Interest inventory helper
# ---------------------------------------------------------------------------

def _upsert_interest_inventory(db: Session, student_id: int) -> Dict[str, Any]:
    """
    Generate 10 random interest inventory answers, compute cluster boosts,
    and upsert into interest_inventory_responses.

    Returns {"answers": ..., "cluster_boosts": ..., "top_clusters": [...]}
    """
    answers: Dict[str, str] = {
        f"q{i}": random.choice(["a", "b", "c"])
        for i in range(1, 11)
    }
    cluster_boosts = _compute_cluster_boosts(answers)

    now = datetime.utcnow()
    existing = (
        db.query(InterestInventoryResponse)
        .filter(
            InterestInventoryResponse.student_id == student_id,
            InterestInventoryResponse.inventory_version == INVENTORY_VERSION,
        )
        .first()
    )

    if existing:
        existing.answers = answers
        existing.cluster_boosts = cluster_boosts
        existing.lang = "en"
        existing.updated_at = now
    else:
        db.add(InterestInventoryResponse(
            student_id=student_id,
            inventory_version=INVENTORY_VERSION,
            answers=answers,
            cluster_boosts=cluster_boosts,
            lang="en",
            submitted_at=now,
            updated_at=now,
        ))

    db.commit()

    top_clusters = sorted(
        cluster_boosts.keys(),
        key=lambda c: cluster_boosts[c],
        reverse=True,
    )[:3]

    return {
        "answers": answers,
        "cluster_boosts": cluster_boosts,
        "top_clusters": top_clusters,
    }


# ---------------------------------------------------------------------------
# Core simulation logic (shared by both endpoints)
# ---------------------------------------------------------------------------

def _simulate_one_assessment(
    db: Session,
    student_user: User,
    student: Student,
    tier: str,
    mode: str,
    persona: Optional[str],
    custom_aq_ranges: Optional[Dict[str, List[int]]],
    context_data: Dict[str, str],
) -> Dict[str, Any]:
    """
    Run the full assessment pipeline for one student using real code paths.

    Returns a result dict on success.
    Raises on failure — caller must catch.
    """
    t_start = time.time()

    # ── Step 1: Update tier on User ──────────────────────────────────────
    student_user.tier = tier
    db.flush()

    # ── Step 2: Create assessment (exact same handler) ───────────────────
    assessment: Assessment = create_assessment(db=db, current_user=student_user)

    # ── Step 3: Fetch sampled questions ──────────────────────────────────
    aq_rows: List[AssessmentQuestion] = (
        db.query(AssessmentQuestion)
        .filter(AssessmentQuestion.assessment_id == assessment.id)
        .all()
    )

    if not aq_rows:
        raise RuntimeError(
            f"No questions sampled for assessment_id={assessment.id}. "
            "Question pool may be empty."
        )

    # ── Step 4: Generate answers per persona / custom ranges ──────────────
    response_objects: List[schemas.AssessmentResponseCreate] = []
    for aq in aq_rows:
        aq_num = _extract_aq_num(aq.question_code or "")
        group = _aq_num_to_group(aq_num) if aq_num is not None else "aq_01_05"
        lo, hi = _get_range(mode, persona, custom_aq_ranges, group)
        answer_int = random.randint(lo, hi)
        # Clamp to valid scale 1-5
        answer_int = max(1, min(5, answer_int))
        response_objects.append(
            schemas.AssessmentResponseCreate(
                question_id=aq.question_id,
                answer=str(answer_int),
                idempotency_key=str(uuid.uuid4()),
            )
        )

    # ── Step 5: Submit all responses (exact same handler) ────────────────
    # BackgroundTasks() is instantiated standalone; tasks are registered but
    # will not fire — submit_assessment below triggers scoring synchronously.
    submit_responses(
        assessment_id=assessment.id,
        responses=response_objects,
        background_tasks=BackgroundTasks(),
        db=db,
        current_user=student_user,
    )

    # ── Step 6: Update context profile before scoring ────────────────────
    ctx: Optional[ContextProfile] = (
        db.query(ContextProfile)
        .filter(ContextProfile.assessment_id == assessment.id)
        .first()
    )
    if ctx is None:
        # Fallback: create it (should already exist from create_assessment)
        _ensure_context_profile_for_assessment(
            db=db, assessment=assessment, current_user_id=student_user.id,
        )
        ctx = db.query(ContextProfile).filter(
            ContextProfile.assessment_id == assessment.id
        ).first()

    if ctx:
        ctx.education_board = context_data.get("education_board", "cbse")
        ctx.ses_band = context_data.get("ses_band", "some")
        ctx.support_level = context_data.get("support_level", "medium")
        ctx.resource_access = context_data.get("resource_access", "moderate")
        ctx.cps_score = float(compute_cps_v1(
            ses_band=ctx.ses_band,
            education_board=ctx.education_board,
            support_level=ctx.support_level,
            resource_access=ctx.resource_access,
            db=db,
        ))
        db.commit()
        db.refresh(ctx)

    cps_used = float(ctx.cps_score) if ctx else 0.0

    # ── Step 7: Submit assessment — triggers full scoring pipeline ────────
    # Calls: B7 compute_and_persist_skill_scores → B8 sync_skill_scores_to_keyskills
    #      → B9 recompute_student_analytics → career engine → AssessmentResult
    submit_assessment(
        assessment_id=assessment.id,
        db=db,
        current_user=student_user,
    )

    # ── Step 8: Generate interest inventory ──────────────────────────────
    interest_result = _upsert_interest_inventory(db=db, student_id=student.id)

    # ── Step 9: Fetch results — use raw career engine for scores ─────────
    raw_careers: List[Dict] = []
    try:
        raw_careers = compute_careers_for_student(
            student_id=student.id,
            assessment_id=assessment.id,
            db=db,
            limit=9,
        )
    except Exception as exc:
        logger.warning(
            "career engine failed post-sim for student_id=%s: %s", student.id, exc
        )

    top_careers = [
        {
            "rank": idx + 1,
            "title": c.get("title") or "Unknown",
            "cluster": c.get("cluster") or "",
            "fit_band": c.get("fit_band_key") or c.get("fit_band") or "",
            "score": round(float(c.get("score") or 0.0), 2),
        }
        for idx, c in enumerate(raw_careers[:9])
    ]

    top_clusters = list(dict.fromkeys(
        c["cluster"] for c in top_careers if c["cluster"]
    ))[:3]

    duration_ms = int((time.time() - t_start) * 1000)

    return {
        "success": True,
        "assessment_id": assessment.id,
        "student_id": student.id,
        "student_email": student_user.email,
        "mode": mode,
        "persona": persona,
        "tier": tier,
        "questions_answered": len(response_objects),
        "interest_answered": len(interest_result["answers"]),
        "context_profile": {
            "education_board": context_data.get("education_board", "cbse"),
            "ses_band": context_data.get("ses_band", "some"),
            "support_level": context_data.get("support_level", "medium"),
            "resource_access": context_data.get("resource_access", "moderate"),
            "cps_score": cps_used,
        },
        "top_careers": top_careers,
        "top_clusters": top_clusters,
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# Pydantic schemas — Endpoint 1
# ---------------------------------------------------------------------------

class ContextInput(BaseModel):
    education_board: str = "cbse"
    ses_band:        str = "some"
    support_level:   str = "medium"
    resource_access: str = "moderate"


class CustomAQRanges(BaseModel):
    aq_01_05: List[int] = Field(default=[3, 4], min_length=2, max_length=2)
    aq_06_09: List[int] = Field(default=[3, 4], min_length=2, max_length=2)
    aq_10_14: List[int] = Field(default=[3, 4], min_length=2, max_length=2)
    aq_15_18: List[int] = Field(default=[3, 4], min_length=2, max_length=2)
    aq_19_22: List[int] = Field(default=[3, 4], min_length=2, max_length=2)
    aq_23_25: List[int] = Field(default=[3, 4], min_length=2, max_length=2)


class SimulateAssessmentRequest(BaseModel):
    student_email:     str
    student_password:  str
    mode:              str = Field("preset", pattern=r"^(preset|custom)$")
    persona:           Optional[str] = "balanced"
    tier:              str = Field("free", pattern=r"^(free|premium)$")
    custom_aq_ranges:  Optional[CustomAQRanges] = None
    context:           Optional[ContextInput] = None

    @model_validator(mode="after")
    def validate_sim_request(self) -> "SimulateAssessmentRequest":
        if self.mode == "preset":
            # Resolve alias before validation so old names keep working
            if self.persona in PERSONA_ALIASES:
                self.persona = PERSONA_ALIASES[self.persona]
            if self.persona not in VALID_PERSONAS:
                raise ValueError(
                    f"Unknown persona '{self.persona}'. "
                    f"Valid: {sorted(VALID_PERSONAS)}"
                )
        if self.mode == "custom" and self.custom_aq_ranges is None:
            raise ValueError("custom_aq_ranges is required when mode='custom'")
        return self


# ---------------------------------------------------------------------------
# Pydantic schemas — Endpoint 2
# ---------------------------------------------------------------------------

class SimulateBatchRequest(BaseModel):
    count:              int = Field(10, ge=1, le=100)
    persona:            str = "mixed"
    tier:               str = Field("free", pattern=r"^(free|premium)$")
    create_students:    bool = True
    base_email_prefix:  str = Field("sim", min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_batch_request(self) -> "SimulateBatchRequest":
        if self.persona != "mixed":
            # Resolve alias before validation so old names keep working
            if self.persona in PERSONA_ALIASES:
                self.persona = PERSONA_ALIASES[self.persona]
            if self.persona not in VALID_PERSONAS:
                raise ValueError(
                    f"Unknown persona '{self.persona}'. "
                    f"Valid: {sorted(VALID_PERSONAS)} or 'mixed'"
                )
        return self


# ---------------------------------------------------------------------------
# GET /simulate/students
# ---------------------------------------------------------------------------

@router.get(
    "/simulate/students",
    summary="List student emails for simulator dropdown (admin)",
    dependencies=[Depends(require_role("admin"))],
)
def list_simulator_students(
    db: Session = Depends(get_db),
    _=Depends(get_current_active_user),
):
    from sqlalchemy import text
    rows = db.execute(
        text("SELECT u.email FROM users u WHERE u.role='student' ORDER BY u.email")
    ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# POST /simulate-assessment
# ---------------------------------------------------------------------------

@router.post(
    "/simulate-assessment",
    status_code=200,
    summary="Run a simulated assessment for an existing student (admin)",
    dependencies=[Depends(require_role("admin"))],
)
def simulate_assessment(
    payload: SimulateAssessmentRequest,
    db: Session = Depends(get_db),
    current_admin: schemas.User = Depends(get_current_active_user),
):
    """
    Run the full assessment pipeline for a student using their real credentials.
    Uses identical code paths as the production student flow.

    The student must already exist. Updates their User.tier before running.
    Context profile is set and CPS is recomputed before scoring.
    Logs to admin_audit_trail (action="simulate", entity_type="assessment").
    """
    # ── Authenticate student ──────────────────────────────────────────────
    student_user: Optional[User] = authenticate_user(
        db, payload.student_email.strip().lower(), payload.student_password
    )
    if student_user is None:
        raise HTTPException(
            status_code=400,
            detail=f"Authentication failed for '{payload.student_email}'. "
                   "Check email and password.",
        )

    student: Optional[Student] = (
        db.query(Student).filter(Student.user_id == student_user.id).first()
    )
    if student is None:
        raise HTTPException(
            status_code=400,
            detail=f"No student profile found for user '{payload.student_email}'. "
                   "Create a student profile first.",
        )

    # ── Build context dict ───────────────────────────────────────────────
    ctx_data = DEFAULT_CONTEXT.copy()
    if payload.context:
        ctx_data = {
            "education_board": payload.context.education_board,
            "ses_band":        payload.context.ses_band,
            "support_level":   payload.context.support_level,
            "resource_access": payload.context.resource_access,
        }

    custom_ranges_dict: Optional[Dict[str, List[int]]] = None
    if payload.mode == "custom" and payload.custom_aq_ranges:
        custom_ranges_dict = {
            "aq_01_05": payload.custom_aq_ranges.aq_01_05,
            "aq_06_09": payload.custom_aq_ranges.aq_06_09,
            "aq_10_14": payload.custom_aq_ranges.aq_10_14,
            "aq_15_18": payload.custom_aq_ranges.aq_15_18,
            "aq_19_22": payload.custom_aq_ranges.aq_19_22,
            "aq_23_25": payload.custom_aq_ranges.aq_23_25,
        }

    # ── Run simulation ────────────────────────────────────────────────────
    try:
        result = _simulate_one_assessment(
            db=db,
            student_user=student_user,
            student=student,
            tier=payload.tier,
            mode=payload.mode,
            persona=payload.persona,
            custom_aq_ranges=custom_ranges_dict,
            context_data=ctx_data,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "simulate_assessment failed for student=%s: %s", payload.student_email, exc
        )
        raise HTTPException(
            status_code=500,
            detail=f"Simulation failed at pipeline step: {exc}",
        )

    # ── Audit log ────────────────────────────────────────────────────────
    log_audit(
        db=db,
        action="simulate",
        entity_type="assessment",
        entity_id=result["assessment_id"],
        entity_name=payload.student_email,
        user_id=current_admin.id,
        user_email=current_admin.email,
        details={
            "mode":    payload.mode,
            "persona": payload.persona,
            "tier":    payload.tier,
            "top_career": result["top_careers"][0]["title"] if result["top_careers"] else None,
        },
        commit=True,
    )

    return result


# ---------------------------------------------------------------------------
# POST /simulate-batch
# ---------------------------------------------------------------------------

@router.post(
    "/simulate-batch",
    status_code=200,
    summary="Bulk-create and simulate assessments for multiple students (admin)",
    dependencies=[Depends(require_role("admin"))],
)
def simulate_batch(
    payload: SimulateBatchRequest,
    db: Session = Depends(get_db),
    current_admin: schemas.User = Depends(get_current_active_user),
):
    """
    Bulk simulate *count* students.

    When create_students=True:
      - Auto-creates User + Student rows with @test.mapyourcareer.in emails
      - Format: {prefix}_{YYYYMMDD}_{seq:03d}@test.mapyourcareer.in
      - Password: SimTest@2026!  |  Grade: 10  |  DOB: 2007-01-01

    When create_students=False:
      - Expects students at {prefix}_*@test.mapyourcareer.in to already exist
      - Returns 400 if none are found

    Each student simulation failure is caught and counted; the batch continues.
    Logs the full batch to admin_audit_trail.
    """
    today_str = datetime.utcnow().strftime("%Y%m%d")
    batch_id = f"{payload.base_email_prefix}_{today_str}"
    sim_password = "SimTest@2026!"
    hashed_sim_pw = get_password_hash(sim_password)
    dob_default = date(2007, 1, 1)

    students_created = 0
    student_pairs: List[tuple[User, Student]] = []  # (user, student)

    # ── Resolve or create students ────────────────────────────────────────
    if payload.create_students:
        seq = 1
        while len(student_pairs) < payload.count:
            email = f"{payload.base_email_prefix}_{today_str}_{seq:03d}@test.mapyourcareer.in"
            seq += 1

            existing_user = (
                db.query(User).filter(User.email == email).first()
            )
            if existing_user:
                # Email already taken — find its student or skip
                existing_student = (
                    db.query(Student)
                    .filter(Student.user_id == existing_user.id)
                    .first()
                )
                if existing_student:
                    student_pairs.append((existing_user, existing_student))
                continue

            display_name = f"Sim Student {len(student_pairs) + 1:03d}"
            try:
                new_user = User(
                    full_name=display_name,
                    email=email,
                    hashed_password=hashed_sim_pw,
                    dob=dob_default,
                    is_minor=False,
                    tier=payload.tier,
                    role="student",
                )
                db.add(new_user)
                db.flush()  # get new_user.id

                new_student = Student(
                    user_id=new_user.id,
                    name=display_name,
                    grade=10,
                )
                db.add(new_student)
                db.flush()

                db.commit()
                db.refresh(new_user)
                db.refresh(new_student)

                student_pairs.append((new_user, new_student))
                students_created += 1

            except Exception as exc:
                db.rollback()
                logger.warning("Failed to create sim student email=%s: %s", email, exc)
                # Try next sequence number

    else:
        # Find existing students at this prefix domain
        like_pattern = f"{payload.base_email_prefix}_%@test.mapyourcareer.in"
        existing_users = (
            db.query(User)
            .filter(User.email.like(like_pattern))
            .limit(payload.count)
            .all()
        )
        if not existing_users:
            raise HTTPException(
                status_code=400,
                detail=f"No existing students found matching '{like_pattern}'. "
                       "Set create_students=true to auto-create them.",
            )
        for u in existing_users:
            s = db.query(Student).filter(Student.user_id == u.id).first()
            if s:
                student_pairs.append((u, s))

    if not student_pairs:
        raise HTTPException(
            status_code=400,
            detail="No students available to simulate. "
                   "Check create_students flag or base_email_prefix.",
        )

    # ── Run simulations ───────────────────────────────────────────────────
    results: List[Dict[str, Any]] = []
    total_succeeded = 0
    total_failed = 0
    personas_used: Counter = Counter()
    clusters_dist: Counter = Counter()
    durations: List[int] = []

    for i, (student_user, student) in enumerate(student_pairs):
        # Determine persona for this student
        if payload.persona == "mixed":
            persona = MIXED_CYCLE[i % len(MIXED_CYCLE)]
        else:
            persona = payload.persona

        ctx_data = DEFAULT_CONTEXT.copy()

        try:
            sim_result = _simulate_one_assessment(
                db=db,
                student_user=student_user,
                student=student,
                tier=payload.tier,
                mode="preset",
                persona=persona,
                custom_aq_ranges=None,
                context_data=ctx_data,
            )

            total_succeeded += 1
            personas_used[persona] += 1
            for cluster in sim_result.get("top_clusters", []):
                clusters_dist[cluster] += 1
            durations.append(sim_result.get("duration_ms", 0))

            top_career = sim_result["top_careers"][0] if sim_result["top_careers"] else {}
            top_cluster = sim_result["top_clusters"][0] if sim_result["top_clusters"] else ""

            results.append({
                "student_email":  student_user.email,
                "persona":        persona,
                "top_career":     top_career.get("title", ""),
                "top_cluster":    top_cluster,
                "assessment_id":  sim_result["assessment_id"],
            })

        except Exception as exc:
            total_failed += 1
            logger.warning(
                "Batch sim failed for student_id=%s email=%s persona=%s: %s",
                student.id, student_user.email, persona, exc,
            )
            results.append({
                "student_email":  student_user.email,
                "persona":        persona,
                "top_career":     None,
                "top_cluster":    None,
                "assessment_id":  None,
                "error":          str(exc),
            })

    avg_duration_ms = int(sum(durations) / len(durations)) if durations else 0

    # ── Audit log ────────────────────────────────────────────────────────
    log_audit(
        db=db,
        action="simulate",
        entity_type="assessment",
        entity_id=None,
        entity_name=f"batch:{batch_id}",
        user_id=current_admin.id,
        user_email=current_admin.email,
        details={
            "batch_id":        batch_id,
            "total_requested": len(student_pairs),
            "total_succeeded": total_succeeded,
            "total_failed":    total_failed,
            "students_created": students_created,
            "persona":         payload.persona,
            "tier":            payload.tier,
        },
        commit=True,
    )

    return {
        "batch_id":        batch_id,
        "total_requested": len(student_pairs),
        "total_succeeded": total_succeeded,
        "total_failed":    total_failed,
        "students_created": students_created,
        "results":         results,
        "summary": {
            "personas_used":         dict(personas_used),
            "clusters_distribution": dict(clusters_dist.most_common()),
            "avg_duration_ms":       avg_duration_ms,
        },
    }
