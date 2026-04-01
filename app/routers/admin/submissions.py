"""
Admin SME Submission router.
Exposes 5 endpoints:

  Admin-authenticated (require_role admin):
    POST /admin/sme/{sme_id}/tokens     — generate submission token for SME+career
    GET  /admin/sme/tokens              — list all tokens with status
    POST /admin/sme/submit              — manual entry fallback (admin submits on behalf)

  Public (token IS the authentication — no login required):
    GET  /sme/form/{token}              — SME retrieves their form (career + AQs + key skills)
    POST /sme/form/{token}/submit       — SME submits ratings + disclaimer acceptance

Role gate:
  Admin endpoints: require_role("admin") via router dependency
  Public endpoints: token-only auth — mounted on a separate public router

Reads/writes:
  sme_submission_tokens, sme_aq_ratings, sme_keyskill_ratings,
  sme_keyskill_suggestions, sme_profiles, careers, keyskills,
  associated_qualities

Rating scale: SME inputs 0–10 integer → stored as 0.0–1.0 (÷10).
Disclaimer: v1.0 (ACTIVE_DISCLAIMER_VERSION). Acceptance stored with
timestamp and IP address per DPDP Act 2023 requirements.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import (
    SMEProfile,
    SMESubmissionToken,
    SMEAQRating,
    SMEKeySkillRating,
    SMEKeySkillSuggestion,
    DISCLAIMER_VERSIONS,
    ACTIVE_DISCLAIMER_VERSION,
)
from app.models import Career, KeySkill
from app.auth.auth import require_role, get_current_active_user

logger = logging.getLogger(__name__)

# ── Admin-authenticated router ────────────────────────────────────────────
router = APIRouter(
    tags=["Admin Panel"],
    dependencies=[Depends(require_role("admin"))],
)

# ── Public router (token-only auth, no login required) ───────────────────
# Mounted separately in main.py under /v1/sme (no /admin prefix)
public_router = APIRouter(
    tags=["SME Form"],
)


# ============================================================
# Pydantic schemas — local to this router
# ============================================================

class TokenCreateRequest(BaseModel):
    """Input for generating a new submission token."""
    career_id:    int
    round_number: int  = Field(1, ge=1, description="Validation round number")
    expires_days: int  = Field(14, ge=1, le=90, description="Days until token expires")


class TokenResponse(BaseModel):
    """Output schema for a submission token."""
    id:           int
    sme_id:       int
    career_id:    int
    token:        str
    round_number: int
    status:       str
    expires_at:   Optional[datetime]
    created_at:   datetime
    submitted_at: Optional[datetime]
    disclaimer_accepted: bool
    sme_name:     Optional[str] = None
    career_title: Optional[str] = None

    model_config = {"from_attributes": True}


class AQRatingInput(BaseModel):
    """Single AQ rating from SME. Input 0–10, stored as 0.0–1.0."""
    aq_code:       str   = Field(..., description="e.g. AQ_01")
    rating:        int   = Field(..., ge=0, le=10, description="0=not relevant, 10=critical")
    confidence:    Optional[int] = Field(None, ge=0, le=10)
    notes:         Optional[str] = None


class KeySkillRatingInput(BaseModel):
    """Single key skill rating from SME. Input 0–10, stored as 0.0–1.0."""
    keyskill_id:   int
    rating:        int   = Field(..., ge=0, le=10)
    confidence:    Optional[int] = Field(None, ge=0, le=10)
    notes:         Optional[str] = None


class KeySkillSuggestionInput(BaseModel):
    """SME suggestion for a key skill not yet mapped to this career."""
    existing_keyskill_id:  Optional[int]  = None
    suggested_name:        Optional[str]  = None
    suggested_description: Optional[str]  = None
    importance_rating:     Optional[int]  = Field(None, ge=0, le=10)
    rationale:             Optional[str]  = None


class SMEFormSubmission(BaseModel):
    """Full form submission from SME."""
    aq_ratings:          List[AQRatingInput]
    keyskill_ratings:    List[KeySkillRatingInput]   = []
    suggestions:         List[KeySkillSuggestionInput] = []
    disclaimer_accepted: bool = Field(..., description="Must be True to submit")


class AdminManualSubmission(BaseModel):
    """Admin manual entry fallback — submit on behalf of SME."""
    token_id:         int
    aq_ratings:       List[AQRatingInput]
    keyskill_ratings: List[KeySkillRatingInput] = []


# ============================================================
# Helper: normalise 0–10 integer to 0.0–1.0 float
# ============================================================

def _normalise(value: Optional[int]) -> Optional[float]:
    """Convert 0–10 SME input to 0.0–1.0 storage format. None → None."""
    if value is None:
        return None
    return round(value / 10.0, 4)


# ============================================================
# Endpoint 1: Generate submission token
# Purpose:    Admin creates a unique token for an SME+career+round
# Input:      Path param sme_id + JSON body TokenCreateRequest
# Writes:     sme_submission_tokens table (1 new row)
# Idempotent: No — duplicate sme+career+round returns 400
# ============================================================

@router.post(
    "/sme/{sme_id}/tokens",
    response_model=TokenResponse,
    status_code=201,
    summary="ADM-B02: Generate a submission token for an SME+career pair",
)
def create_submission_token(
    sme_id:  int,
    payload: TokenCreateRequest,
    db:      Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Generate a unique UUID token for an SME+career+round combination.
    The token URL is: /sme/form/{token}
    Send this URL to the SME via email (ADM-B05 scheduler handles bulk sending).
    Returns 404 if SME or career not found.
    Returns 400 if a token already exists for this SME+career+round.
    """
    sme = db.query(SMEProfile).filter(SMEProfile.id == sme_id).first()
    if not sme:
        raise HTTPException(status_code=404, detail=f"SME id={sme_id} not found.")
    if sme.status == "inactive":
        raise HTTPException(status_code=400, detail=f"SME id={sme_id} is inactive. Reactivate before generating tokens.")

    career = db.query(Career).filter(Career.id == payload.career_id).first()
    if not career:
        raise HTTPException(status_code=404, detail=f"Career id={payload.career_id} not found.")

    # Guard: no duplicate token for same SME+career+round
    existing = db.query(SMESubmissionToken).filter(
        SMESubmissionToken.sme_id      == sme_id,
        SMESubmissionToken.career_id   == payload.career_id,
        SMESubmissionToken.round_number == payload.round_number,
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Token already exists for SME {sme_id} + career {payload.career_id} + round {payload.round_number}. "
                   f"Token status: {existing.status}.",
        )

    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_days)

    token = SMESubmissionToken(
        sme_id       = sme_id,
        career_id    = payload.career_id,
        token        = str(uuid.uuid4()),
        round_number = payload.round_number,
        status       = "pending",
        expires_at   = expires_at,
        disclaimer_accepted = False,
    )
    db.add(token)
    db.commit()
    db.refresh(token)

    logger.info("Token created: id=%s sme=%s career=%s round=%s expires=%s",
                token.id, sme_id, payload.career_id, payload.round_number, expires_at.date())

    result = TokenResponse.model_validate(token)
    result.sme_name    = sme.full_name
    result.career_title = career.title
    return result


# ============================================================
# Endpoint 2: List all tokens
# Purpose:    Admin views all tokens with their status
# Input:      Optional ?status=pending|submitted|expired filter
# Reads:      sme_submission_tokens table
# Idempotent: Yes — read-only
# ============================================================

@router.get(
    "/sme/tokens",
    response_model=List[TokenResponse],
    summary="ADM-B02: List all SME submission tokens",
)
def list_tokens(
    status: Optional[str] = Query(None, description="Filter: pending | submitted | expired"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Return all submission tokens, optionally filtered by status.
    Each token shows sme_name and career_title for readability.
    """
    if status and status not in ("pending", "submitted", "expired"):
        raise HTTPException(status_code=400, detail="status must be pending, submitted, or expired")

    query = db.query(SMESubmissionToken)
    if status:
        query = query.filter(SMESubmissionToken.status == status)

    tokens = query.order_by(SMESubmissionToken.created_at.desc()).all()

    results = []
    for t in tokens:
        r = TokenResponse.model_validate(t)
        r.sme_name    = t.sme.full_name if t.sme else None
        r.career_title = t.career.title  if t.career else None
        results.append(r)
    return results


# ============================================================
# Endpoint 3: Admin manual submission fallback
# Purpose:    Admin enters SME ratings directly (when SME cannot use the form)
# Input:      JSON body AdminManualSubmission
# Writes:     sme_aq_ratings, sme_keyskill_ratings
# Idempotent: No — duplicate submission returns 400
# ============================================================

@router.post(
    "/sme/submit",
    status_code=201,
    summary="ADM-B02: Admin manual entry — submit ratings on behalf of SME",
)
def admin_manual_submit(
    payload: AdminManualSubmission,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Admin fallback: enter ratings manually on behalf of an SME.
    Marks disclaimer_accepted=True and records admin user as submitter.
    Used when SME cannot access the email link (e.g. phone-based expert panels).
    """
    token = db.query(SMESubmissionToken).filter(
        SMESubmissionToken.id == payload.token_id
    ).first()
    if not token:
        raise HTTPException(status_code=404, detail=f"Token id={payload.token_id} not found.")
    if token.status == "submitted":
        raise HTTPException(status_code=400, detail="This token has already been submitted.")
    if token.status == "expired":
        raise HTTPException(status_code=400, detail="This token has expired.")

    _write_ratings(db, token, payload.aq_ratings, payload.keyskill_ratings, [])

    # Mark disclaimer accepted by admin on behalf of SME
    token.disclaimer_accepted    = True
    token.disclaimer_version     = ACTIVE_DISCLAIMER_VERSION
    token.disclaimer_accepted_at = datetime.now(timezone.utc)
    token.disclaimer_ip_address  = "admin-manual-entry"
    token.status       = "submitted"
    token.submitted_at = datetime.now(timezone.utc)
    db.commit()

    logger.info("Admin manual submission: token=%s sme=%s career=%s by admin=%s",
                token.id, token.sme_id, token.career_id, current_user.id)
    return {"message": f"Ratings submitted for token {token.id} by admin."}


# ============================================================
# Public Endpoint 4: Get SME form
# Purpose:    SME retrieves their form — career info + AQs + key skills to rate
# Input:      Path param token (UUID)
# Reads:      sme_submission_tokens, careers, associated_qualities, keyskills
# Idempotent: Yes — read-only
# ============================================================

@public_router.get(
    "/sme/form/{token}",
    summary="ADM-B02: SME retrieves their submission form (public, token-auth)",
)
def get_sme_form(
    token: str,
    db:    Session = Depends(get_db),
):
    """
    Public endpoint — no login required.
    Token knowledge = authorisation.
    Returns the SME's name, career details, list of AQs to rate,
    and list of pre-mapped key skills to rate.
    Also returns the active disclaimer text for display on the form.
    Returns 404 if token not found, 400 if expired or already submitted.
    """
    token_row = db.query(SMESubmissionToken).filter(
        SMESubmissionToken.token == token
    ).first()
    if not token_row:
        raise HTTPException(status_code=404, detail="Invalid or expired form link.")
    if token_row.status == "submitted":
        raise HTTPException(status_code=400, detail="This form has already been submitted. Thank you!")
    if token_row.status == "expired":
        raise HTTPException(status_code=400, detail="This form link has expired. Please contact MapYourCareer admin.")
    if token_row.expires_at and datetime.now(timezone.utc) > token_row.expires_at:
        token_row.status = "expired"
        db.commit()
        raise HTTPException(status_code=400, detail="This form link has expired. Please contact MapYourCareer admin.")

    # Fetch AQs (all 25)
    from app.models import AssociatedQuality
    aqs = db.query(AssociatedQuality).order_by(AssociatedQuality.aq_id).all()

    # Fetch key skills mapped to this career
    career = token_row.career
    mapped_keyskills = career.keyskills if career else []

    return {
        "token":       token,
        "sme_name":    token_row.sme.full_name if token_row.sme else None,
        "career":      {"id": career.id, "title": career.title, "description": career.description} if career else None,
        "round_number": token_row.round_number,
        "expires_at":  token_row.expires_at,
        "disclaimer": {
            "version": ACTIVE_DISCLAIMER_VERSION,
            "text":    DISCLAIMER_VERSIONS[ACTIVE_DISCLAIMER_VERSION],
        },
        "aqs": [
            {"aq_code": aq.aq_id, "aq_name": aq.aq_name}
            for aq in aqs
        ],
        "keyskills": [
            {"id": ks.id, "name": ks.name, "description": ks.description}
            for ks in mapped_keyskills
        ],
    }


# ============================================================
# Public Endpoint 5: SME submits their form
# Purpose:    SME submits AQ + key skill ratings + optional suggestions
# Input:      Path param token + JSON body SMEFormSubmission
# Writes:     sme_aq_ratings, sme_keyskill_ratings, sme_keyskill_suggestions
#             Updates sme_submission_tokens status + disclaimer audit fields
# Idempotent: No — duplicate submission returns 400
# ============================================================

@public_router.post(
    "/sme/form/{token}/submit",
    status_code=201,
    summary="ADM-B02: SME submits ratings via form link (public, token-auth)",
)
def submit_sme_form(
    token:   str,
    payload: SMEFormSubmission,
    request: Request,
    db:      Session = Depends(get_db),
):
    """
    Public endpoint — no login required. Token = authorisation.
    Validates:
    - Token exists and is pending (not submitted or expired)
    - disclaimer_accepted must be True (enforced by frontend checkbox)
    - All 25 AQs must be rated (no partial submissions)
    Stores disclaimer acceptance with timestamp and IP (DPDP Act compliance).
    Updates submission_count on SMEProfile after successful submission.
    """
    token_row = db.query(SMESubmissionToken).filter(
        SMESubmissionToken.token == token
    ).first()
    if not token_row:
        raise HTTPException(status_code=404, detail="Invalid or expired form link.")
    if token_row.status == "submitted":
        raise HTTPException(status_code=400, detail="This form has already been submitted. Thank you!")
    if token_row.status == "expired":
        raise HTTPException(status_code=400, detail="This form link has expired.")
    if token_row.expires_at and datetime.now(timezone.utc) > token_row.expires_at:
        token_row.status = "expired"
        db.commit()
        raise HTTPException(status_code=400, detail="This form link has expired.")

    # Disclaimer must be accepted before submission
    if not payload.disclaimer_accepted:
        raise HTTPException(
            status_code=400,
            detail="You must accept the confidentiality disclaimer before submitting.",
        )

    # All 25 AQs must be rated
    if len(payload.aq_ratings) != 25:
        raise HTTPException(
            status_code=400,
            detail=f"All 25 AQs must be rated. Received {len(payload.aq_ratings)} ratings.",
        )

    # Write ratings
    _write_ratings(db, token_row, payload.aq_ratings, payload.keyskill_ratings, payload.suggestions)

    # Record disclaimer acceptance (DPDP Act audit trail)
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    token_row.disclaimer_accepted    = True
    token_row.disclaimer_version     = ACTIVE_DISCLAIMER_VERSION
    token_row.disclaimer_accepted_at = datetime.now(timezone.utc)
    token_row.disclaimer_ip_address  = client_ip[:45]  # truncate to column length

    # Mark token as submitted
    token_row.status       = "submitted"
    token_row.submitted_at = datetime.now(timezone.utc)

    # Increment SME submission count
    if token_row.sme:
        token_row.sme.submission_count += 1

    db.commit()

    logger.info("SME form submitted: token=%s sme=%s career=%s aq_count=%s ks_count=%s ip=%s",
                token_row.id, token_row.sme_id, token_row.career_id,
                len(payload.aq_ratings), len(payload.keyskill_ratings), client_ip)

    return {
        "message": "Thank you! Your ratings have been submitted successfully.",
        "submitted_at": token_row.submitted_at,
        "aq_ratings_saved": len(payload.aq_ratings),
        "keyskill_ratings_saved": len(payload.keyskill_ratings),
        "suggestions_saved": len(payload.suggestions),
    }


# ============================================================
# Internal helper: write ratings to DB
# Used by both public submit and admin manual submit endpoints
# ============================================================

def _write_ratings(
    db:               Session,
    token_row:        SMESubmissionToken,
    aq_ratings:       list,
    keyskill_ratings: list,
    suggestions:      list,
):
    """
    Write AQ ratings, key skill ratings, and suggestions to the DB.
    Called by both submit_sme_form and admin_manual_submit.
    Does NOT commit — caller is responsible for db.commit().
    """
    # AQ ratings
    for r in aq_ratings:
        db.add(SMEAQRating(
            token_id      = token_row.id,
            sme_id        = token_row.sme_id,
            career_id     = token_row.career_id,
            aq_code       = r.aq_code,
            weight_rating = _normalise(r.rating),
            confidence    = _normalise(r.confidence),
            notes         = r.notes,
        ))

    # Key skill ratings
    for r in keyskill_ratings:
        db.add(SMEKeySkillRating(
            token_id      = token_row.id,
            sme_id        = token_row.sme_id,
            career_id     = token_row.career_id,
            keyskill_id   = r.keyskill_id,
            weight_rating = _normalise(r.rating),
            confidence    = _normalise(r.confidence),
            notes         = r.notes,
        ))

    # Key skill suggestions
    for s in suggestions:
        db.add(SMEKeySkillSuggestion(
            token_id              = token_row.id,
            sme_id                = token_row.sme_id,
            career_id             = token_row.career_id,
            existing_keyskill_id  = s.existing_keyskill_id,
            suggested_name        = s.suggested_name,
            suggested_description = s.suggested_description,
            importance_rating     = _normalise(s.importance_rating),
            rationale             = s.rationale,
        ))
