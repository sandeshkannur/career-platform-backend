"""
Admin counsellor-account management.

Endpoints (all admin-only, mounted under /v1/admin):
  POST   /counsellors        — create a counsellor User (role="counsellor")
  GET    /counsellors        — list counsellor accounts (limit/offset pagination)
  GET    /counsellors/{id}   — single counsellor detail
  PATCH  /counsellors/{id}   — update name / email / active status
  DELETE /counsellors/{id}   — SOFT delete only (sets is_active=false)

Conventions:
  - Password hashing reuses auth.get_password_hash (same as public signup);
    there is deliberately NO public route for counsellor creation.
  - Every mutation is recorded in admin_audit_trail via log_audit.
  - Soft delete never removes the row; any future counsellor_assignments
    history must stay intact for audit purposes.

Follow-ups (out of scope here):
  - Caseload count on the detail endpoint once the counsellor_assignments
    table lands (feat/counsellor-assignments-phase1 has not merged yet).
  - get_current_active_user does not enforce users.is_active yet, so a
    deactivated counsellor can still log in until that check is added.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app import models
from app.deps import get_db
from app.auth.auth import require_role, get_password_hash
from app.routers.admin.audit_trail import log_audit

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Admin Panel"],
    dependencies=[Depends(require_role("admin"))],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class CounsellorCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(..., min_length=8)
    dob: date
    phone_number: Optional[str] = Field(None, max_length=20)


class CounsellorUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


class CounsellorOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    dob: date
    phone_number: Optional[str]
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class CounsellorListOut(BaseModel):
    total: int
    limit: int
    offset: int
    counsellors: list[CounsellorOut]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_counsellor_or_404(db: Session, counsellor_id: int) -> models.User:
    user = (
        db.query(models.User)
        .filter(models.User.id == counsellor_id, models.User.role == "counsellor")
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Counsellor not found: {counsellor_id}",
        )
    return user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/counsellors",
    response_model=CounsellorOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a counsellor account (admin)",
)
def create_counsellor(
    payload: CounsellorCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    email_normalized = payload.email.strip().lower()

    if db.query(models.User).filter(models.User.email == email_normalized).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Mirror the signup handler's is_minor derivation (users.is_minor is NOT NULL)
    today = datetime.utcnow().date()
    age = (
        today.year
        - payload.dob.year
        - ((today.month, today.day) < (payload.dob.month, payload.dob.day))
    )

    counsellor = models.User(
        full_name=payload.full_name.strip(),
        email=email_normalized,
        hashed_password=get_password_hash(payload.password),
        dob=payload.dob,
        is_minor=age < 18,
        phone_number=(payload.phone_number or "").strip() or None,
        role="counsellor",
        is_active=True,
    )
    db.add(counsellor)
    db.flush()  # get counsellor.id for the audit row

    log_audit(
        db,
        action="create",
        entity_type="counsellor",
        entity_id=counsellor.id,
        entity_name=counsellor.email,
        user_id=current_user.id,
        user_email=current_user.email,
        details={"full_name": counsellor.full_name},
    )
    db.commit()
    db.refresh(counsellor)
    return counsellor


@router.get(
    "/counsellors",
    response_model=CounsellorListOut,
    summary="List counsellor accounts (admin)",
)
def list_counsellors(
    include_inactive: bool = Query(True, description="Include deactivated counsellors"),
    limit: int = Query(50, ge=1, le=200, description="Max items to return (default 50, max 200)"),
    offset: int = Query(0, ge=0, description="Pagination offset (default 0)"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_role("admin")),
):
    q = db.query(models.User).filter(models.User.role == "counsellor")
    if not include_inactive:
        q = q.filter(models.User.is_active.is_(True))

    total = q.count()
    rows = q.order_by(models.User.id).offset(offset).limit(limit).all()
    return CounsellorListOut(
        total=total,
        limit=limit,
        offset=offset,
        counsellors=rows,
    )


@router.get(
    "/counsellors/{counsellor_id}",
    response_model=CounsellorOut,
    summary="Counsellor detail (admin)",
)
def get_counsellor(
    counsellor_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_role("admin")),
):
    # Caseload count intentionally absent: counsellor_assignments does not
    # exist yet (feat/counsellor-assignments-phase1 unmerged). Add the join
    # here once that table lands.
    return _get_counsellor_or_404(db, counsellor_id)


@router.patch(
    "/counsellors/{counsellor_id}",
    response_model=CounsellorOut,
    summary="Update counsellor details (admin)",
)
def update_counsellor(
    counsellor_id: int,
    payload: CounsellorUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    counsellor = _get_counsellor_or_404(db, counsellor_id)

    changes: dict = {}

    if payload.full_name is not None and payload.full_name.strip() != counsellor.full_name:
        changes["full_name"] = {"old": counsellor.full_name, "new": payload.full_name.strip()}
        counsellor.full_name = payload.full_name.strip()

    if payload.email is not None:
        email_normalized = payload.email.strip().lower()
        if email_normalized != counsellor.email:
            clash = (
                db.query(models.User)
                .filter(models.User.email == email_normalized, models.User.id != counsellor.id)
                .first()
            )
            if clash:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered",
                )
            changes["email"] = {"old": counsellor.email, "new": email_normalized}
            counsellor.email = email_normalized

    if payload.is_active is not None and payload.is_active != counsellor.is_active:
        changes["is_active"] = {"old": counsellor.is_active, "new": payload.is_active}
        counsellor.is_active = payload.is_active

    if changes:
        log_audit(
            db,
            action="update",
            entity_type="counsellor",
            entity_id=counsellor.id,
            entity_name=counsellor.email,
            user_id=current_user.id,
            user_email=current_user.email,
            details=changes,
        )
        db.commit()
        db.refresh(counsellor)

    return counsellor


@router.delete(
    "/counsellors/{counsellor_id}",
    response_model=CounsellorOut,
    summary="Deactivate a counsellor (soft delete, admin)",
)
def deactivate_counsellor(
    counsellor_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    """
    SOFT delete only: sets is_active=false and keeps the row (platform
    convention — never hard-delete). Any counsellor_assignments history
    (once that table exists) must be left untouched for audit purposes.
    """
    counsellor = _get_counsellor_or_404(db, counsellor_id)

    if counsellor.is_active:
        counsellor.is_active = False
        log_audit(
            db,
            action="delete",
            entity_type="counsellor",
            entity_id=counsellor.id,
            entity_name=counsellor.email,
            user_id=current_user.id,
            user_email=current_user.email,
            details={"soft_delete": True, "is_active": {"old": True, "new": False}},
        )
        db.commit()
        db.refresh(counsellor)

    return counsellor
