"""
Admin SME (Subject Matter Expert) router.
Exposes 4 endpoints under /v1/admin/sme/:
  POST   /admin/sme            — create a new SME profile
  GET    /admin/sme            — list all SME profiles (filterable by status)
  PUT    /admin/sme/{sme_id}   — update an existing SME profile
  DELETE /admin/sme/{sme_id}   — soft-deactivate an SME (sets status=inactive)

Role gate: admin only (inherited from router dependency).
Reads/writes: sme_profiles table.

Weighting note:
  effective_weight = credentials_score × calibration_score
  credentials_score is recomputed on every create/update from the 4 input fields.
  calibration_score is set externally by the aggregation service (ADM-B03).
  effective_weight is never stored — always computed fresh by ADM-B03.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import SMEProfile
from app.auth.auth import require_role, get_current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Admin Panel"],
    dependencies=[Depends(require_role("admin"))],
)


# ============================================================
# Pydantic schemas — local to this router (SME-specific only)
# ============================================================

class SMECreateRequest(BaseModel):
    """Input schema for creating a new SME profile."""
    full_name:        str            = Field(..., min_length=2, max_length=200)
    email:            EmailStr
    career_assignments: Optional[str] = Field(None, description="Comma-separated career IDs. Max 3 careers.")
    years_experience: Optional[int]  = Field(None, ge=0, le=60)
    seniority_score:  Optional[float]= Field(None, ge=0.0, le=1.0)
    education_score:  Optional[float]= Field(None, ge=0.0, le=1.0)
    sector_relevance: Optional[float]= Field(None, ge=0.0, le=1.0)
    sector:           Optional[str]  = Field(None, max_length=200)
    education:        Optional[str]  = Field(None, max_length=200)


class SMEUpdateRequest(BaseModel):
    """Input schema for updating an existing SME profile. All fields optional."""
    full_name:         Optional[str]   = Field(None, min_length=2, max_length=200)
    career_assignments:Optional[str]   = None
    years_experience:  Optional[int]   = Field(None, ge=0, le=60)
    seniority_score:   Optional[float] = Field(None, ge=0.0, le=1.0)
    education_score:   Optional[float] = Field(None, ge=0.0, le=1.0)
    sector_relevance:  Optional[float] = Field(None, ge=0.0, le=1.0)
    sector:            Optional[str]   = Field(None, max_length=200)
    education:         Optional[str]   = Field(None, max_length=200)


class SMEResponse(BaseModel):
    """Output schema for a single SME profile."""
    id:                int
    full_name:         str
    email:             str
    career_assignments:Optional[str]
    years_experience:  Optional[int]
    seniority_score:   Optional[float]
    education_score:   Optional[float]
    sector_relevance:  Optional[float]
    credentials_score: Optional[float]
    calibration_score: Optional[float]
    submission_count:  int
    sector:            Optional[str]
    education:         Optional[str]
    status:            str

    model_config = {"from_attributes": True}


# ============================================================
# Helper: compute credentials_score from the 4 input fields
# Formula: (years×0.4) + (seniority×0.3) + (education×0.2) + (sector×0.1)
# Returns None if all 4 inputs are None (profile not yet scored).
# ============================================================

def _compute_credentials_score(
    years_experience:  Optional[int],
    seniority_score:   Optional[float],
    education_score:   Optional[float],
    sector_relevance:  Optional[float],
) -> Optional[float]:
    """
    Compute the credential score from the 4 weighting inputs.
    Missing inputs are treated as 0.0 so partial profiles still get a score.
    Returns None only if ALL four inputs are None (profile has no data yet).
    """
    if all(v is None for v in [years_experience, seniority_score,
                                education_score, sector_relevance]):
        return None

    # Normalise years_experience to 0.0–1.0 (cap at 30 years = 1.0)
    years_norm = min((years_experience or 0) / 30.0, 1.0)

    score = (
        years_norm                  * 0.4
        + (seniority_score  or 0.0) * 0.3
        + (education_score  or 0.0) * 0.2
        + (sector_relevance or 0.0) * 0.1
    )
    return round(score, 4)


# ============================================================
# Endpoint 1: Create SME profile
# Purpose:    Register a new Subject Matter Expert in the system
# Input:      JSON body — SMECreateRequest
# Writes:     sme_profiles table (1 new row)
# Idempotent: No — duplicate email returns 400
# ============================================================

@router.post(
    "/sme",
    response_model=SMEResponse,
    status_code=201,
    summary="ADM-B01: Create a new SME profile",
)
def create_sme(
    payload: SMECreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Create a new SME profile.
    Automatically computes credentials_score from the 4 weighting inputs.
    calibration_score starts as None — set by aggregation service after first round.
    Returns 400 if email already exists (active or inactive).
    """
    # Guard: unique email across all statuses (active + inactive)
    existing = db.query(SMEProfile).filter(SMEProfile.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"SME with email '{payload.email}' already exists (status: {existing.status}). "
                   "Use PUT /admin/sme/{id} to reactivate or update.",
        )

    # Validate career assignment cap (max 3 careers per SME)
    if payload.career_assignments:
        career_ids = [c.strip() for c in payload.career_assignments.split(",") if c.strip()]
        if len(career_ids) > 3:
            raise HTTPException(
                status_code=400,
                detail=f"SME may be assigned to a maximum of 3 careers. Got {len(career_ids)}.",
            )

    # Compute credentials_score from inputs
    credentials_score = _compute_credentials_score(
        payload.years_experience,
        payload.seniority_score,
        payload.education_score,
        payload.sector_relevance,
    )

    sme = SMEProfile(
        full_name=payload.full_name,
        email=payload.email,
        career_assignments=payload.career_assignments,
        years_experience=payload.years_experience,
        seniority_score=payload.seniority_score,
        education_score=payload.education_score,
        sector_relevance=payload.sector_relevance,
        credentials_score=credentials_score,
        calibration_score=None,  # set by ADM-B03 aggregation service
        submission_count=0,
        sector=payload.sector,
        education=payload.education,
        status="active",
    )

    db.add(sme)
    db.commit()
    db.refresh(sme)

    logger.info("SME created: id=%s email=%s credentials_score=%s",
                sme.id, sme.email, sme.credentials_score)
    return sme


# ============================================================
# Endpoint 2: List SME profiles
# Purpose:    Return all SME profiles, optionally filtered by status
# Input:      Query param ?status=active|inactive (default: all)
# Reads:      sme_profiles table
# Idempotent: Yes — read-only
# ============================================================

@router.get(
    "/sme",
    response_model=List[SMEResponse],
    summary="ADM-B01: List all SME profiles",
)
def list_smes(
    status: Optional[str] = Query(
        None,
        description="Filter by status: 'active' or 'inactive'. Omit for all.",
    ),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Return all SME profiles.
    Use ?status=active to show only active SMEs.
    Use ?status=inactive to show deactivated SMEs.
    Omit the parameter to return all regardless of status.
    """
    query = db.query(SMEProfile)
    if status:
        if status not in ("active", "inactive"):
            raise HTTPException(
                status_code=400,
                detail="status must be 'active' or 'inactive'",
            )
        query = query.filter(SMEProfile.status == status)

    return query.order_by(SMEProfile.full_name).all()


# ============================================================
# Endpoint 3: Update SME profile
# Purpose:    Update any field on an existing SME profile
# Input:      JSON body — SMEUpdateRequest (all fields optional)
# Writes:     sme_profiles table (1 row updated)
# Idempotent: Yes — same payload produces same result
# ============================================================

@router.put(
    "/sme/{sme_id}",
    response_model=SMEResponse,
    summary="ADM-B01: Update an existing SME profile",
)
def update_sme(
    sme_id: int,
    payload: SMEUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Update an SME profile by ID.
    Credential inputs (years, seniority, education, sector) automatically
    recompute credentials_score when any of them change.
    calibration_score is NOT touched here — managed by ADM-B03 only.
    Works on both active and inactive profiles.
    """
    sme = db.query(SMEProfile).filter(SMEProfile.id == sme_id).first()
    if not sme:
        raise HTTPException(status_code=404, detail=f"SME id={sme_id} not found.")

    # Apply only the fields that were provided
    if payload.full_name is not None:
        sme.full_name = payload.full_name
    if payload.career_assignments is not None:
        career_ids = [c.strip() for c in payload.career_assignments.split(",") if c.strip()]
        if len(career_ids) > 3:
            raise HTTPException(
                status_code=400,
                detail=f"SME may be assigned to a maximum of 3 careers. Got {len(career_ids)}.",
            )
        sme.career_assignments = payload.career_assignments
    if payload.years_experience is not None:
        sme.years_experience = payload.years_experience
    if payload.seniority_score is not None:
        sme.seniority_score = payload.seniority_score
    if payload.education_score is not None:
        sme.education_score = payload.education_score
    if payload.sector_relevance is not None:
        sme.sector_relevance = payload.sector_relevance
    if payload.sector is not None:
        sme.sector = payload.sector
    if payload.education is not None:
        sme.education = payload.education

    # Recompute credentials_score whenever any credential input changes
    sme.credentials_score = _compute_credentials_score(
        sme.years_experience,
        sme.seniority_score,
        sme.education_score,
        sme.sector_relevance,
    )

    db.commit()
    db.refresh(sme)

    logger.info("SME updated: id=%s credentials_score=%s", sme.id, sme.credentials_score)
    return sme


# ============================================================
# Endpoint 4: Deactivate SME (soft delete)
# Purpose:    Mark an SME as inactive — preserves audit trail
# Input:      Path param sme_id
# Writes:     sme_profiles table (status = 'inactive')
# Idempotent: Yes — deactivating an already-inactive SME is a no-op
# ============================================================

@router.delete(
    "/sme/{sme_id}",
    summary="ADM-B01: Deactivate an SME profile (soft delete)",
)
def deactivate_sme(
    sme_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Soft-deactivate an SME by setting status = 'inactive'.
    The row is NEVER deleted — this preserves the audit trail
    of which SMEs validated which careers and when.
    Deactivating an already-inactive SME is a safe no-op.
    """
    sme = db.query(SMEProfile).filter(SMEProfile.id == sme_id).first()
    if not sme:
        raise HTTPException(status_code=404, detail=f"SME id={sme_id} not found.")

    if sme.status == "inactive":
        return {"message": f"SME id={sme_id} is already inactive. No change made."}

    sme.status = "inactive"
    db.commit()

    logger.info("SME deactivated: id=%s email=%s", sme.id, sme.email)
    return {"message": f"SME id={sme_id} ({sme.email}) deactivated successfully."}
