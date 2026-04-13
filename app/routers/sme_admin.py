"""
SME submission endpoints — mounted at /v1/admin/sme/

Routes:
  POST   /submit                    — receive a new SME form submission
  GET    /submissions               — list all submissions (admin only)
  GET    /submissions/{id}          — single submission detail (admin only)
  PUT    /submissions/{id}/status   — update status + notes (admin only)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import Career, SMEProfile, SMESubmission
from app.auth.auth import require_role, get_current_active_user
from app import schemas

router = APIRouter(tags=["SME Submissions"])


# ---------------------------------------------------------------------------
# Pydantic schemas (local — no impact on existing schema modules)
# ---------------------------------------------------------------------------

VALID_STATUSES = {"received", "under_review", "approved", "rejected"}


class SMESubmitRequest(BaseModel):
    sme_email: EmailStr
    career_id: int
    submission_data: Dict[str, Any]
    idempotency_key: str


class SMESubmitResponse(BaseModel):
    id: int
    status: str
    submitted_at: datetime

    model_config = {"from_attributes": True}


class SMESubmissionDetail(BaseModel):
    id: int
    sme_id: Optional[int]
    sme_email: str
    career_id: int
    submission_data: Dict[str, Any]
    idempotency_key: str
    status: str
    submitted_at: datetime
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[int]
    notes: Optional[str]

    model_config = {"from_attributes": True}


class SMEStatusUpdateRequest(BaseModel):
    status: str
    notes: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return v


# ---------------------------------------------------------------------------
# POST /submit
# ---------------------------------------------------------------------------

@router.post(
    "/submit",
    response_model=SMESubmitResponse,
    summary="Submit SME career data (idempotent)",
)
def submit_sme_form(
    body: SMESubmitRequest,
    db: Session = Depends(get_db),
):
    # Idempotency check — return existing record without creating a duplicate
    existing = (
        db.query(SMESubmission)
        .filter(SMESubmission.idempotency_key == body.idempotency_key)
        .first()
    )
    if existing:
        return existing

    # Validate career_id
    career = db.query(Career).filter(Career.id == body.career_id).first()
    if not career:
        raise HTTPException(status_code=404, detail=f"Career {body.career_id} not found")

    # Resolve sme_id from email if a profile exists
    sme_profile = (
        db.query(SMEProfile)
        .filter(SMEProfile.email == str(body.sme_email))
        .first()
    )
    sme_id = sme_profile.id if sme_profile else None

    submission = SMESubmission(
        sme_id=sme_id,
        sme_email=str(body.sme_email),
        career_id=body.career_id,
        submission_data=body.submission_data,
        idempotency_key=body.idempotency_key,
        status="received",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


# ---------------------------------------------------------------------------
# GET /submissions  (admin only)
# ---------------------------------------------------------------------------

@router.get(
    "/submissions",
    response_model=List[SMESubmissionDetail],
    summary="List all SME submissions (admin)",
    dependencies=[Depends(require_role("admin"))],
)
def list_submissions(
    status: Optional[str] = Query(None, description="Filter by status"),
    career_id: Optional[int] = Query(None, description="Filter by career_id"),
    sme_email: Optional[str] = Query(None, description="Filter by sme_email (exact match)"),
    db: Session = Depends(get_db),
):
    q = db.query(SMESubmission)
    if status is not None:
        q = q.filter(SMESubmission.status == status)
    if career_id is not None:
        q = q.filter(SMESubmission.career_id == career_id)
    if sme_email is not None:
        q = q.filter(SMESubmission.sme_email == sme_email)
    return q.order_by(SMESubmission.submitted_at.desc()).all()


# ---------------------------------------------------------------------------
# GET /submissions/{id}  (admin only)
# ---------------------------------------------------------------------------

@router.get(
    "/submissions/{submission_id}",
    response_model=SMESubmissionDetail,
    summary="Get single SME submission (admin)",
    dependencies=[Depends(require_role("admin"))],
)
def get_submission(
    submission_id: int,
    db: Session = Depends(get_db),
):
    submission = db.query(SMESubmission).filter(SMESubmission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    return submission


# ---------------------------------------------------------------------------
# PUT /submissions/{id}/status  (admin only)
# ---------------------------------------------------------------------------

@router.put(
    "/submissions/{submission_id}/status",
    response_model=SMESubmissionDetail,
    summary="Update submission status (admin)",
)
def update_submission_status(
    submission_id: int,
    body: SMEStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(require_role("admin")),
):
    submission = db.query(SMESubmission).filter(SMESubmission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    submission.status = body.status
    submission.reviewed_at = datetime.now(timezone.utc)
    submission.reviewed_by = current_user.id
    if body.notes is not None:
        submission.notes = body.notes

    db.commit()
    db.refresh(submission)
    return submission
