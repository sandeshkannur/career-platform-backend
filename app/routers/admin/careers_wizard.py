"""
Admin career wizard endpoint — single-call career creation.

  POST /v1/admin/careers/wizard

Creates three rows in a single transaction:
  1. careers            — core career record
  2. career_content     — EN language content block
  3. career_keyskill_association — weighted key-skill mappings (3–10 rows)

Logs the creation to admin_audit_trail.

Does NOT touch any scoring or assessment tables.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import Career, CareerCluster, CareerContent, KeySkill, career_keyskill_association
from app.auth.auth import require_role, get_current_active_user
from app.routers.admin.audit_trail import log_audit
from app import schemas

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class KeySkillMapping(BaseModel):
    keyskill_id:      int = Field(..., ge=1)
    weight_percentage: int = Field(..., ge=1, le=100)


class CareerWizardRequest(BaseModel):
    # ── Required core fields ──────────────────────────────────────────────
    title:       str = Field(..., min_length=2, max_length=255)
    career_code: str = Field(..., min_length=2, max_length=50)

    # ── Optional core fields ──────────────────────────────────────────────
    cluster_id:         Optional[int] = None
    description:        Optional[str] = None
    recommended_stream: Optional[str] = Field(None, max_length=50)

    # ── Salary / market data ──────────────────────────────────────────────
    salary_entry_inr: Optional[int] = Field(None, ge=0)
    salary_mid_inr:   Optional[int] = Field(None, ge=0)
    salary_peak_inr:  Optional[int] = Field(None, ge=0)
    automation_risk:  Optional[str] = Field(None, max_length=20)
    future_outlook:   Optional[str] = Field(None, max_length=20)

    # ── EN content block (career_content) ────────────────────────────────
    indian_job_title:   Optional[str] = None
    prestige_title:     Optional[str] = None
    pathway_step1:      Optional[str] = None
    pathway_step2:      Optional[str] = None
    pathway_step3:      Optional[str] = None
    pathway_accessible: Optional[str] = None
    pathway_premium:    Optional[str] = None
    pathway_earn_learn: Optional[str] = None

    # ── Key-skill mappings ────────────────────────────────────────────────
    keyskill_mappings: List[KeySkillMapping] = Field(
        ..., min_length=3, max_length=10,
        description="3–10 key skill mappings whose weight_percentage values must sum to 100",
    )

    @model_validator(mode="after")
    def validate_wizard(self) -> "CareerWizardRequest":
        # career_code: normalise to uppercase, strip whitespace
        self.career_code = self.career_code.strip().upper()

        # Salary ordering: entry ≤ mid ≤ peak (only checked when all three present)
        s_entry = self.salary_entry_inr
        s_mid   = self.salary_mid_inr
        s_peak  = self.salary_peak_inr
        if s_entry is not None and s_mid is not None and s_entry > s_mid:
            raise ValueError("salary_entry_inr must be ≤ salary_mid_inr")
        if s_mid is not None and s_peak is not None and s_mid > s_peak:
            raise ValueError("salary_mid_inr must be ≤ salary_peak_inr")
        if s_entry is not None and s_peak is not None and s_entry > s_peak:
            raise ValueError("salary_entry_inr must be ≤ salary_peak_inr")

        # Duplicate keyskill_ids
        ks_ids = [m.keyskill_id for m in self.keyskill_mappings]
        if len(ks_ids) != len(set(ks_ids)):
            raise ValueError("keyskill_mappings contains duplicate keyskill_id values")

        # Weights must sum to exactly 100
        total = sum(m.weight_percentage for m in self.keyskill_mappings)
        if total != 100:
            raise ValueError(
                f"keyskill_mappings weight_percentage values must sum to 100 (got {total})"
            )

        return self


class CareerWizardResponse(BaseModel):
    id:          int
    title:       str
    career_code: str
    cluster_id:  Optional[int]
    message:     str


# ---------------------------------------------------------------------------
# POST /careers/wizard
# ---------------------------------------------------------------------------

@router.post(
    "/careers/wizard",
    response_model=CareerWizardResponse,
    status_code=201,
    summary="Create a new career with content and key-skill mappings (admin wizard)",
    dependencies=[Depends(require_role("admin"))],
)
def career_wizard(
    payload: CareerWizardRequest,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """
    Single-call career creation.

    Inserts a `careers` row, a `career_content` EN row, and all
    `career_keyskill_association` rows in one transaction.
    Rolls back entirely if any step fails.
    Logs the creation to admin_audit_trail.
    """
    # ── Validation: career_code uniqueness ────────────────────────────────
    if db.query(Career).filter(Career.career_code == payload.career_code).first():
        raise HTTPException(
            status_code=400,
            detail=f"career_code '{payload.career_code}' already exists.",
        )

    # ── Validation: title uniqueness ──────────────────────────────────────
    if db.query(Career).filter(Career.title == payload.title).first():
        raise HTTPException(
            status_code=400,
            detail=f"A career with title '{payload.title}' already exists.",
        )

    # ── Validation: cluster exists ────────────────────────────────────────
    if payload.cluster_id is not None:
        if not db.query(CareerCluster).filter(CareerCluster.id == payload.cluster_id).first():
            raise HTTPException(
                status_code=404,
                detail=f"CareerCluster id={payload.cluster_id} not found.",
            )

    # ── Validation: all keyskill_ids exist ───────────────────────────────
    requested_ks_ids = {m.keyskill_id for m in payload.keyskill_mappings}
    found_ks = db.query(KeySkill.id).filter(KeySkill.id.in_(requested_ks_ids)).all()
    found_ks_ids = {row.id for row in found_ks}
    missing = requested_ks_ids - found_ks_ids
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"KeySkill id(s) not found: {sorted(missing)}",
        )

    # ── Single transaction: INSERT career + content + associations ────────
    try:
        # 1. careers row
        career = Career(
            title               = payload.title,
            career_code         = payload.career_code,
            cluster_id          = payload.cluster_id,
            description         = payload.description,
            recommended_stream  = payload.recommended_stream,
            salary_entry_inr    = payload.salary_entry_inr,
            salary_mid_inr      = payload.salary_mid_inr,
            salary_peak_inr     = payload.salary_peak_inr,
            automation_risk     = payload.automation_risk,
            future_outlook      = payload.future_outlook,
            is_active           = True,
        )
        db.add(career)
        db.flush()  # assigns career.id without committing

        # 2. career_content EN row
        content = CareerContent(
            career_id        = career.id,
            lang             = "en",
            description      = payload.description,
            indian_job_title = payload.indian_job_title,
            prestige_title   = payload.prestige_title,
            pathway_step1    = payload.pathway_step1,
            pathway_step2    = payload.pathway_step2,
            pathway_step3    = payload.pathway_step3,
            pathway_accessible = payload.pathway_accessible,
            pathway_premium    = payload.pathway_premium,
            pathway_earn_learn = payload.pathway_earn_learn,
        )
        db.add(content)

        # 3. career_keyskill_association rows (association table with extra column)
        db.execute(
            insert(career_keyskill_association),
            [
                {
                    "career_id":         career.id,
                    "keyskill_id":       m.keyskill_id,
                    "weight_percentage": m.weight_percentage,
                }
                for m in payload.keyskill_mappings
            ],
        )

        # 4. Audit trail (same transaction — rolls back with everything else)
        log_audit(
            db          = db,
            action      = "create",
            entity_type = "career",
            entity_id   = career.id,
            entity_name = payload.title,
            user_id     = current_user.id,
            user_email  = current_user.email,
            details     = {
                "career_code":      payload.career_code,
                "cluster_id":       payload.cluster_id,
                "keyskill_count":   len(payload.keyskill_mappings),
                "keyskill_ids":     [m.keyskill_id for m in payload.keyskill_mappings],
            },
        )

        db.commit()
        db.refresh(career)

        logger.info(
            "Career wizard: created career id=%s code=%s by admin=%s",
            career.id, career.career_code, current_user.email,
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Career wizard failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Career creation failed: {exc}")

    return CareerWizardResponse(
        id          = career.id,
        title       = career.title,
        career_code = career.career_code,
        cluster_id  = career.cluster_id,
        message     = (
            f"Career '{career.title}' created successfully with "
            f"{len(payload.keyskill_mappings)} key skill mapping(s)."
        ),
    )
