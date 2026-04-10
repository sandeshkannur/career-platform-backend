"""
Admin DPDP compliance metrics endpoint.
Auth: inherited from the admin package router (require_role("admin")).

GET /v1/admin/compliance/dpdp
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.deps import get_db
from app import models

router = APIRouter(prefix="/compliance")

_DATA_RETENTION_DAYS = 365 * 3   # 3-year default retention policy
_MINOR_CONSENT_THRESHOLD = 18    # years


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
