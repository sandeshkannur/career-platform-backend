"""
Counsellor-student access checks (phase 1: shadow mode, log-only).

has_counsellor_access() answers "does this counsellor have an active
assignment for this student?" from counsellor_assignments.

shadow_check_counsellor_access() is the phase-1 wrapper the read endpoints
call: for counsellor requesters ONLY, it logs a WARNING when no active
assignment exists and does nothing else. It never raises and never alters
the response — enforcement is a later phase. Admin and student access is
deliberately not inspected at all.
"""
from __future__ import annotations

import logging

from sqlalchemy import exists, and_
from sqlalchemy.orm import Session

from app import models

logger = logging.getLogger(__name__)


def has_counsellor_access(db: Session, counsellor_id: int, student_id: int) -> bool:
    """True if an ACTIVE counsellor_assignments row links the pair."""
    return bool(
        db.query(
            exists().where(
                and_(
                    models.CounsellorAssignment.counsellor_id == counsellor_id,
                    models.CounsellorAssignment.student_id == student_id,
                    models.CounsellorAssignment.active.is_(True),
                )
            )
        ).scalar()
    )


def shadow_check_counsellor_access(
    db: Session,
    current_user: models.User,
    student_id: int,
    endpoint: str,
) -> None:
    """
    Phase-1 shadow check: log-only, completely inert for the caller.

    Only inspects requests where current_user.role == "counsellor"; all
    other roles return immediately. Any internal error is swallowed (and
    logged) so the check can never affect the endpoint's response.
    """
    try:
        if (getattr(current_user, "role", None) or "").strip().lower() != "counsellor":
            return
        if not has_counsellor_access(db, current_user.id, student_id):
            logger.warning(
                "counsellor-access shadow check: counsellor user_id=%s email=%s "
                "accessed student_id=%s via %s with no active assignment "
                "(phase 1: log-only, request not blocked)",
                current_user.id,
                getattr(current_user, "email", "?"),
                student_id,
                endpoint,
            )
    except Exception as exc:  # pragma: no cover — must never break the endpoint
        logger.warning("counsellor-access shadow check errored (endpoint=%s): %s", endpoint, exc)
