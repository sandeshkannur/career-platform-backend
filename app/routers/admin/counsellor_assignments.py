"""
Admin counsellor-assignment management (phase 1).

Endpoints (all admin-only, mounted under /v1/admin):
  POST   /counsellor-assignments                  — manually assign a counsellor to a student
  GET    /counsellor-assignments?counsellor_id=N  — list a counsellor's caseload
  DELETE /counsellor-assignments/{assignment_id}  — deactivate (soft, sets active=false)

Conventions:
  - Every mutation is recorded in admin_audit_trail via log_audit
    (entity_type="counsellor_assignment").
  - Soft-remove only: rows are never hard-deleted (platform convention);
    history stays intact for audit purposes.
  - No uniqueness on student_id — multiple active counsellors per student is
    a confirmed product decision. Exact duplicates (same counsellor, same
    student, still active) are rejected with 409 to keep caseloads clean.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app import models
from app.deps import get_db
from app.auth.auth import require_role
from app.routers.admin.audit_trail import log_audit

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Admin Panel"],
    dependencies=[Depends(require_role("admin"))],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AssignmentCreate(BaseModel):
    counsellor_id: int
    student_id: int


class AssignmentOut(BaseModel):
    id: int
    counsellor_id: int
    student_id: int
    student_name: Optional[str]
    assignment_type: str
    assigned_by: Optional[int]
    assigned_at: datetime
    active: bool

    model_config = {"from_attributes": True}


class CaseloadOut(BaseModel):
    counsellor_id: int
    total: int
    assignments: list[AssignmentOut]


def _assignment_out(assignment: models.CounsellorAssignment) -> AssignmentOut:
    """Serialize an assignment row, resolving student_name via the relationship."""
    return AssignmentOut(
        id=assignment.id,
        counsellor_id=assignment.counsellor_id,
        student_id=assignment.student_id,
        student_name=assignment.student.name if assignment.student else None,
        assignment_type=assignment.assignment_type,
        assigned_by=assignment.assigned_by,
        assigned_at=assignment.assigned_at,
        active=assignment.active,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_active_counsellor_or_404(db: Session, counsellor_id: int) -> models.User:
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


def _get_student_or_404(db: Session, student_id: int) -> models.Student:
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student not found: {student_id}",
        )
    return student


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/counsellor-assignments",
    response_model=AssignmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a counsellor to a student (admin)",
)
def create_assignment(
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    _get_active_counsellor_or_404(db, payload.counsellor_id)
    _get_student_or_404(db, payload.student_id)

    duplicate = (
        db.query(models.CounsellorAssignment)
        .filter(
            models.CounsellorAssignment.counsellor_id == payload.counsellor_id,
            models.CounsellorAssignment.student_id == payload.student_id,
            models.CounsellorAssignment.active.is_(True),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active assignment already exists (id={duplicate.id})",
        )

    assignment = models.CounsellorAssignment(
        counsellor_id=payload.counsellor_id,
        student_id=payload.student_id,
        assignment_type="admin_assigned",
        assigned_by=current_user.id,
        active=True,
    )
    db.add(assignment)
    db.flush()  # get assignment.id for the audit row

    log_audit(
        db,
        action="create",
        entity_type="counsellor_assignment",
        entity_id=assignment.id,
        user_id=current_user.id,
        user_email=current_user.email,
        details={
            "assignment_type": "admin_assigned",
            "counsellor_id": payload.counsellor_id,
            "student_id": payload.student_id,
        },
    )
    db.commit()
    db.refresh(assignment)
    return _assignment_out(assignment)


@router.get(
    "/counsellor-assignments",
    response_model=CaseloadOut,
    summary="List a counsellor's caseload (admin)",
)
def list_caseload(
    counsellor_id: int = Query(..., description="Counsellor users.id whose caseload to list"),
    include_inactive: bool = Query(False, description="Include deactivated assignments"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_role("admin")),
):
    _get_active_counsellor_or_404(db, counsellor_id)

    q = (
        db.query(models.CounsellorAssignment)
        .options(joinedload(models.CounsellorAssignment.student))
        .filter(models.CounsellorAssignment.counsellor_id == counsellor_id)
    )
    if not include_inactive:
        q = q.filter(models.CounsellorAssignment.active.is_(True))

    rows = q.order_by(models.CounsellorAssignment.assigned_at.desc()).all()
    return CaseloadOut(
        counsellor_id=counsellor_id,
        total=len(rows),
        assignments=[_assignment_out(r) for r in rows],
    )


@router.delete(
    "/counsellor-assignments/{assignment_id}",
    response_model=AssignmentOut,
    summary="Deactivate an assignment (soft delete, admin)",
)
def deactivate_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    """SOFT delete only: sets active=false and keeps the row (platform convention)."""
    assignment = (
        db.query(models.CounsellorAssignment)
        .filter(models.CounsellorAssignment.id == assignment_id)
        .first()
    )
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment not found: {assignment_id}",
        )

    if assignment.active:
        assignment.active = False
        log_audit(
            db,
            action="delete",
            entity_type="counsellor_assignment",
            entity_id=assignment.id,
            user_id=current_user.id,
            user_email=current_user.email,
            details={
                "soft_delete": True,
                "counsellor_id": assignment.counsellor_id,
                "student_id": assignment.student_id,
                "active": {"old": True, "new": False},
            },
        )
        db.commit()
        db.refresh(assignment)

    return _assignment_out(assignment)
