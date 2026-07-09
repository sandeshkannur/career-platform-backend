"""
Counsellor self-service endpoints, mounted under /v1/counsellor.

Endpoints (counsellor-only):
  POST /students/{student_id}/claim — self-claim a student
    (assignment_type="self_claimed", assigned_by=NULL)

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
from sqlalchemy.orm import Session

from app import models
from app.deps import get_db
from app.auth.auth import require_role
from app.routers.admin.audit_trail import log_audit

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Counsellor"],
    dependencies=[Depends(require_role("counsellor"))],
)


class ClaimOut(BaseModel):
    id: int
    counsellor_id: int
    student_id: int
    assignment_type: str
    assigned_by: Optional[int]
    assigned_at: datetime
    active: bool

    model_config = {"from_attributes": True}


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
    return assignment
