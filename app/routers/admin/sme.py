"""
Admin SME (Subject Matter Expert) router.
Exposes 5 endpoints under /v1/admin/sme/:
  GET    /admin/sme            — list all SME profiles (search + filter)
  GET    /admin/sme/{id}       — get single SME profile
  POST   /admin/sme            — create a new SME profile
  PUT    /admin/sme/{id}       — update an existing SME profile
  DELETE /admin/sme/{id}       — soft-deactivate (sets status=inactive)

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
# Pydantic schemas
# ============================================================

class SMEProfileCreate(BaseModel):
    full_name:          str            = Field(..., min_length=2, max_length=200)
    email:              EmailStr
    phone:              Optional[str]  = Field(None, max_length=50)
    organization:       Optional[str]  = Field(None, max_length=200)
    designation:        Optional[str]  = Field(None, max_length=200)
    expertise_domain:   Optional[str]  = Field(None, max_length=100)
    career_assignments: Optional[str]  = Field(None, description="Comma-separated career IDs. Length <= max_careers.")
    max_careers:        int            = Field(3, ge=1, le=10)
    years_experience:   Optional[int]  = Field(None, ge=0, le=60)
    seniority_score:    Optional[float]= Field(None, ge=0.0, le=1.0)
    education_score:    Optional[float]= Field(None, ge=0.0, le=1.0)
    sector_relevance:   Optional[float]= Field(None, ge=0.0, le=1.0)
    sector:             Optional[str]  = Field(None, max_length=200)
    education:          Optional[str]  = Field(None, max_length=200)
    notes:              Optional[str]  = None


class SMEProfileUpdate(BaseModel):
    full_name:          Optional[str]  = Field(None, min_length=2, max_length=200)
    phone:              Optional[str]  = Field(None, max_length=50)
    organization:       Optional[str]  = Field(None, max_length=200)
    designation:        Optional[str]  = Field(None, max_length=200)
    expertise_domain:   Optional[str]  = Field(None, max_length=100)
    career_assignments: Optional[str]  = None
    max_careers:        Optional[int]  = Field(None, ge=1, le=10)
    years_experience:   Optional[int]  = Field(None, ge=0, le=60)
    seniority_score:    Optional[float]= Field(None, ge=0.0, le=1.0)
    education_score:    Optional[float]= Field(None, ge=0.0, le=1.0)
    sector_relevance:   Optional[float]= Field(None, ge=0.0, le=1.0)
    sector:             Optional[str]  = Field(None, max_length=200)
    education:          Optional[str]  = Field(None, max_length=200)
    notes:              Optional[str]  = None


class SMEProfileOut(BaseModel):
    id:                 int
    full_name:          str
    email:              str
    phone:              Optional[str]
    organization:       Optional[str]
    designation:        Optional[str]
    expertise_domain:   Optional[str]
    career_assignments: Optional[str]
    max_careers:        int
    years_experience:   Optional[int]
    seniority_score:    Optional[float]
    education_score:    Optional[float]
    sector_relevance:   Optional[float]
    credentials_score:  Optional[float]
    calibration_score:  Optional[float]
    submission_count:   int
    sector:             Optional[str]
    education:          Optional[str]
    notes:              Optional[str]
    status:             str
    is_active:          bool

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_row(cls, sme: SMEProfile) -> "SMEProfileOut":
        data = {c.name: getattr(sme, c.name) for c in sme.__table__.columns}
        data["is_active"] = sme.status == "active"
        return cls(**data)


# ============================================================
# Helper: compute credentials_score
# Formula: (years×0.4) + (seniority×0.3) + (education×0.2) + (sector×0.1)
# Returns None only if all 4 inputs are None.
# ============================================================

def _compute_credentials_score(
    years_experience:  Optional[int],
    seniority_score:   Optional[float],
    education_score:   Optional[float],
    sector_relevance:  Optional[float],
) -> Optional[float]:
    if all(v is None for v in [years_experience, seniority_score,
                                education_score, sector_relevance]):
        return None
    years_norm = min((years_experience or 0) / 30.0, 1.0)
    score = (
        years_norm                  * 0.4
        + (seniority_score  or 0.0) * 0.3
        + (education_score  or 0.0) * 0.2
        + (sector_relevance or 0.0) * 0.1
    )
    return round(score, 4)


def _career_count(career_assignments: Optional[str]) -> int:
    if not career_assignments:
        return 0
    return len([c for c in career_assignments.split(",") if c.strip()])


# ============================================================
# GET /sme — list with search + filters
# ============================================================

@router.get("/sme", response_model=List[SMEProfileOut], summary="List SME profiles")
def list_smes(
    search:           Optional[str]  = Query(None, description="Search by name or email (case-insensitive)"),
    is_active:        Optional[bool] = Query(None, description="Filter by active status"),
    expertise_domain: Optional[str]  = Query(None, description="Filter by expertise_domain (exact, case-insensitive)"),
    db: Session = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = db.query(SMEProfile)

    if is_active is not None:
        q = q.filter(SMEProfile.status == ("active" if is_active else "inactive"))

    if expertise_domain:
        q = q.filter(SMEProfile.expertise_domain.ilike(expertise_domain))

    if search:
        pattern = f"%{search}%"
        q = q.filter(
            (SMEProfile.full_name.ilike(pattern)) | (SMEProfile.email.ilike(pattern))
        )

    rows = q.order_by(SMEProfile.full_name).all()
    return [SMEProfileOut.from_orm_row(r) for r in rows]


# ============================================================
# GET /sme/{id} — single profile
# ============================================================

@router.get("/sme/{sme_id}", response_model=SMEProfileOut, summary="Get single SME profile")
def get_sme(
    sme_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_active_user),
):
    sme = db.query(SMEProfile).filter(SMEProfile.id == sme_id).first()
    if not sme:
        raise HTTPException(status_code=404, detail=f"SME id={sme_id} not found.")
    return SMEProfileOut.from_orm_row(sme)


# ============================================================
# POST /sme — create
# ============================================================

@router.post("/sme", response_model=SMEProfileOut, status_code=201, summary="Create SME profile")
def create_sme(
    payload: SMEProfileCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_active_user),
):
    existing = db.query(SMEProfile).filter(SMEProfile.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"SME with email '{payload.email}' already exists (status: {existing.status}). "
                   "Use PUT /admin/sme/{id} to update.",
        )

    count = _career_count(payload.career_assignments)
    if count > payload.max_careers:
        raise HTTPException(
            status_code=400,
            detail=f"career_assignments has {count} entries but max_careers={payload.max_careers}.",
        )

    credentials_score = _compute_credentials_score(
        payload.years_experience, payload.seniority_score,
        payload.education_score,  payload.sector_relevance,
    )

    sme = SMEProfile(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        organization=payload.organization,
        designation=payload.designation,
        expertise_domain=payload.expertise_domain,
        career_assignments=payload.career_assignments,
        max_careers=payload.max_careers,
        years_experience=payload.years_experience,
        seniority_score=payload.seniority_score,
        education_score=payload.education_score,
        sector_relevance=payload.sector_relevance,
        credentials_score=credentials_score,
        calibration_score=None,
        submission_count=0,
        sector=payload.sector,
        education=payload.education,
        notes=payload.notes,
        status="active",
    )

    db.add(sme)
    db.commit()
    db.refresh(sme)
    logger.info("SME created: id=%s email=%s", sme.id, sme.email)
    return SMEProfileOut.from_orm_row(sme)


# ============================================================
# PUT /sme/{id} — update
# ============================================================

@router.put("/sme/{sme_id}", response_model=SMEProfileOut, summary="Update SME profile")
def update_sme(
    sme_id: int,
    payload: SMEProfileUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_active_user),
):
    sme = db.query(SMEProfile).filter(SMEProfile.id == sme_id).first()
    if not sme:
        raise HTTPException(status_code=404, detail=f"SME id={sme_id} not found.")

    # Apply provided fields
    simple_fields = (
        "full_name", "phone", "organization", "designation",
        "expertise_domain", "notes", "sector", "education",
        "years_experience", "seniority_score", "education_score", "sector_relevance",
    )
    for field in simple_fields:
        val = getattr(payload, field, None)
        if val is not None:
            setattr(sme, field, val)

    if payload.max_careers is not None:
        sme.max_careers = payload.max_careers

    if payload.career_assignments is not None:
        cap = payload.max_careers if payload.max_careers is not None else sme.max_careers
        count = _career_count(payload.career_assignments)
        if count > cap:
            raise HTTPException(
                status_code=400,
                detail=f"career_assignments has {count} entries but max_careers={cap}.",
            )
        sme.career_assignments = payload.career_assignments

    # Recompute credentials_score whenever credential inputs change
    sme.credentials_score = _compute_credentials_score(
        sme.years_experience, sme.seniority_score,
        sme.education_score,  sme.sector_relevance,
    )

    db.commit()
    db.refresh(sme)
    logger.info("SME updated: id=%s credentials_score=%s", sme.id, sme.credentials_score)
    return SMEProfileOut.from_orm_row(sme)


# ============================================================
# DELETE /sme/{id} — soft delete (status=inactive)
# ============================================================

@router.delete("/sme/{sme_id}", summary="Soft-delete SME profile (set is_active=false)")
def deactivate_sme(
    sme_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_active_user),
):
    """
    Soft-deactivates an SME by setting status='inactive'.
    The row is NEVER deleted — preserves audit trail for ADM-B03.
    Idempotent: deactivating an already-inactive SME is a no-op.
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
