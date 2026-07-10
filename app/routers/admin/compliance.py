"""
Admin DPDP compliance metrics endpoint.
Auth: inherited from the admin package router (require_role("admin")).

GET /v1/admin/compliance/dpdp
GET /v1/admin/compliance/consent-history/{student_id}
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.deps import get_db
from app import models

router = APIRouter(prefix="/compliance")

_DATA_RETENTION_DAYS = 365 * 3   # 3-year default retention policy
_MINOR_CONSENT_THRESHOLD = 18    # years


# ---------------------------------------------------------------------------
# Pydantic response schemas — consent history
# ---------------------------------------------------------------------------

class ConsentLogEntryOut(BaseModel):
    """
    One consent_logs row. Deliberately excludes token_jti (a token
    identifier, not compliance data) and ip/user_agent (the guardian's
    request metadata, not the student's — an admin compliance view has no
    reason to see them).
    """
    id: int
    status: str
    guardian_email: str
    guardian_locale: Optional[str]
    created_at: datetime
    verified_at: Optional[datetime]
    reason: Optional[str]

    model_config = {"from_attributes": True}


class StudentConsentHistoryOut(BaseModel):
    student_id: int
    student_user_id: Optional[int]
    consented: bool
    consented_at: Optional[datetime]
    entries: List[ConsentLogEntryOut]


@router.get("/dpdp", summary="DPDP compliance metrics (admin)")
def get_dpdp_compliance(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Returns platform-wide DPDP Act 2023 compliance metrics:
    - Student counts (total, minors)
    - Consent rates (overall, minors)
    - Recent consent log entries (last 20 verified events)
    - Pending deletion count (stub — 0 until deletion queue is implemented)
    """

    # ── 1. Total students ────────────────────────────────────────────────
    total_students: int = db.query(func.count(models.User.id)).filter(
        models.User.role == "student"
    ).scalar() or 0

    # ── 2. Minor students (is_minor=True on users table) ─────────────────
    minor_students: int = db.query(func.count(models.User.id)).filter(
        models.User.role == "student",
        models.User.is_minor == True,
    ).scalar() or 0

    # ── 3. Consent rate: students who have at least one verified consent log
    #       We use the consent_logs table (status='verified').
    #       A student is "consented" if any verified log exists for them.
    students_with_consent: int = (
        db.query(func.count(func.distinct(models.ConsentLog.student_user_id)))
        .filter(models.ConsentLog.status == "verified")
        .scalar()
        or 0
    )
    consent_rate: float = (
        round(students_with_consent / total_students * 100, 1)
        if total_students > 0
        else 0.0
    )

    # ── 4. Minor consent rate ─────────────────────────────────────────────
    # Minor students who have a verified guardian consent log
    minor_user_ids_subq = (
        db.query(models.User.id)
        .filter(models.User.role == "student", models.User.is_minor == True)
        .subquery()
    )
    minors_with_consent: int = (
        db.query(func.count(func.distinct(models.ConsentLog.student_user_id)))
        .filter(
            models.ConsentLog.status == "verified",
            models.ConsentLog.student_user_id.in_(minor_user_ids_subq),
        )
        .scalar()
        or 0
    )
    minor_consent_rate: float = (
        round(minors_with_consent / minor_students * 100, 1)
        if minor_students > 0
        else 0.0
    )

    # ── 5. Recent consent logs (last 20 verified) ─────────────────────────
    recent_rows = (
        db.query(models.ConsentLog)
        .filter(models.ConsentLog.status == "verified")
        .order_by(models.ConsentLog.created_at.desc())
        .limit(20)
        .all()
    )
    recent_consents: List[Dict[str, Any]] = [
        {
            "student_user_id": r.student_user_id,
            "student_id": r.student_id,
            "consent_type": "guardian_consent",
            "guardian_email": r.guardian_email,
            "consented_at": r.verified_at.isoformat() if r.verified_at else r.created_at.isoformat(),
        }
        for r in recent_rows
    ]

    # ── 6. Pending deletions (stub — deletion queue not yet implemented) ──
    pending_deletions: int = 0

    return {
        "total_students": total_students,
        "minor_students": minor_students,
        "students_with_consent": students_with_consent,
        "consent_rate": consent_rate,
        "minors_with_consent": minors_with_consent,
        "minor_consent_rate": minor_consent_rate,
        "data_retention_days": _DATA_RETENTION_DAYS,
        "pending_deletions": pending_deletions,
        "recent_consents": recent_consents,
    }


@router.get(
    "/consent-history/{student_id}",
    response_model=StudentConsentHistoryOut,
    summary="Guardian consent history for a student (admin, DPDP audit)",
)
def get_student_consent_history(
    student_id: int,
    db: Session = Depends(get_db),
) -> StudentConsentHistoryOut:
    """
    Full consent_logs history for one student, newest first, plus a derived
    current state: has this student's guardian consented, and when.

    "Consented" is true if ANY row for this student is status='verified' —
    not just the latest row — since a verified consent is not undone by a
    later attempt (e.g. a stray/duplicate re-verify rejected as
    already_verified). consented_at is the verified_at of that row.
    """
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student not found: {student_id}",
        )

    rows = (
        db.query(models.ConsentLog)
        .filter(models.ConsentLog.student_id == student_id)
        .order_by(models.ConsentLog.created_at.desc())
        .all()
    )

    verified_row = next((r for r in rows if r.status == "verified"), None)

    return StudentConsentHistoryOut(
        student_id=student_id,
        student_user_id=student.user_id,
        consented=verified_row is not None,
        consented_at=verified_row.verified_at if verified_row else None,
        entries=rows,
    )
