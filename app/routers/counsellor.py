"""
Counsellor self-service endpoints, mounted under /v1/counsellor.

Endpoints (counsellor-only):
  POST /students/{student_id}/claim — self-claim a student
    (assignment_type="self_claimed", assigned_by=NULL)
  GET  /students                    — own ACTIVE caseload (no params;
    counsellor derived from the token)
  GET  /students/{student_id}       — basic info for an ASSIGNED student;
    403 when no active assignment links the pair. This is the first real
    enforcement point of the assignment system — deliberately scoped to
    this self-view endpoint only; the phase-1 shadow-checked endpoints
    (scorecard, admin-student-analytics, interest inventory) stay log-only.

Product decision (phase 1): self-claims succeed instantly — there is NO
approval step. Instead, every self-claim is written to admin_audit_trail
(entity_type="counsellor_assignment", action="create") so admins have full
after-the-fact visibility via GET /v1/admin/audit-trail.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app import models
from app.deps import get_db
from app.auth.auth import require_role
from app.routers.admin.audit_trail import log_audit
from app.routers.admin.counsellor_assignments import (
    AssignmentOut,
    CaseloadOut,
    _assignment_out,
)
from app.services.counsellor_access import has_counsellor_access

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Counsellor"],
    dependencies=[Depends(require_role("counsellor"))],
)


class ClaimOut(BaseModel):
    id: int
    counsellor_id: int
    student_id: int
    student_name: Optional[str]
    assignment_type: str
    assigned_by: Optional[int]
    assigned_at: datetime
    active: bool

    model_config = {"from_attributes": True}


class AssignedStudentOut(BaseModel):
    student_id: int
    name: str
    grade: Optional[int]
    assignment: AssignmentOut


@router.get(
    "/students",
    response_model=CaseloadOut,
    summary="My active caseload (counsellor)",
)
def my_caseload(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("counsellor")),
):
    """
    The requesting counsellor's own ACTIVE assignments. Same shape as the
    admin caseload endpoint (GET /v1/admin/counsellor-assignments); an empty
    caseload returns total=0 with an empty list, not an error.
    """
    rows = (
        db.query(models.CounsellorAssignment)
        .options(joinedload(models.CounsellorAssignment.student))
        .filter(
            models.CounsellorAssignment.counsellor_id == current_user.id,
            models.CounsellorAssignment.active.is_(True),
        )
        .order_by(models.CounsellorAssignment.assigned_at.desc())
        .all()
    )
    return CaseloadOut(
        counsellor_id=current_user.id,
        total=len(rows),
        assignments=[_assignment_out(r) for r in rows],
    )


@router.get(
    "/students/{student_id}",
    response_model=AssignedStudentOut,
    summary="Basic info for one ASSIGNED student (counsellor)",
)
def get_assigned_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("counsellor")),
):
    """
    Basic student info, only when an ACTIVE assignment links this counsellor
    to this student. 403 otherwise — the first real enforcement point of the
    assignment system, deliberately scoped to this endpoint only (phase-1
    shadow-checked endpoints remain log-only). The 403 fires before any
    student lookup, so it does not leak whether the student id exists.
    """
    if not has_counsellor_access(db, current_user.id, student_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active assignment for this student",
        )

    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:  # defensive: FK guarantees existence for assigned rows
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student not found: {student_id}",
        )

    assignment = (
        db.query(models.CounsellorAssignment)
        .options(joinedload(models.CounsellorAssignment.student))
        .filter(
            models.CounsellorAssignment.counsellor_id == current_user.id,
            models.CounsellorAssignment.student_id == student_id,
            models.CounsellorAssignment.active.is_(True),
        )
        .order_by(models.CounsellorAssignment.assigned_at.desc())
        .first()
    )

    return AssignedStudentOut(
        student_id=student.id,
        name=student.name,
        grade=student.grade,
        assignment=_assignment_out(assignment),
    )


@router.post(
    "/students/{student_id}/claim",
    response_model=ClaimOut,
    status_code=status.HTTP_201_CREATED,
    summary="Self-claim a student (counsellor)",
)
def claim_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("counsellor")),
):
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student not found: {student_id}",
        )

    duplicate = (
        db.query(models.CounsellorAssignment)
        .filter(
            models.CounsellorAssignment.counsellor_id == current_user.id,
            models.CounsellorAssignment.student_id == student_id,
            models.CounsellorAssignment.active.is_(True),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have an active assignment for this student (id={duplicate.id})",
        )

    assignment = models.CounsellorAssignment(
        counsellor_id=current_user.id,
        student_id=student_id,
        assignment_type="self_claimed",
        assigned_by=None,  # self-claimed: no assigning admin
        active=True,
    )
    db.add(assignment)
    db.flush()  # get assignment.id for the audit row

    # Admin visibility without an approval gate: every self-claim lands in
    # the append-only admin_audit_trail immediately.
    log_audit(
        db,
        action="create",
        entity_type="counsellor_assignment",
        entity_id=assignment.id,
        entity_name=student.name,
        user_id=current_user.id,
        user_email=current_user.email,
        details={
            "assignment_type": "self_claimed",
            "counsellor_id": current_user.id,
            "student_id": student_id,
        },
    )
    db.commit()
    db.refresh(assignment)
    return ClaimOut(
        id=assignment.id,
        counsellor_id=assignment.counsellor_id,
        student_id=assignment.student_id,
        student_name=student.name,
        assignment_type=assignment.assignment_type,
        assigned_by=assignment.assigned_by,
        assigned_at=assignment.assigned_at,
        active=assignment.active,
    )
