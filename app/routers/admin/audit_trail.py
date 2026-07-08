"""
Admin audit trail — append-only log of admin actions.

Endpoints (all admin-only):
  GET /v1/admin/audit-trail — list entries, newest first, max 100 per call
      Filters: ?entity_type=  ?action=  ?user_email=  ?from_date=  ?to_date=

Append-only enforcement:
  Any attempt to DELETE /v1/admin/audit-trail or individual entries returns
  405 Method Not Allowed at the route level.

Helper (importable by other admin routers):
  log_audit(db, action, entity_type, ...) — inserts one row, fire-and-forget.
  Safe to call inside a request handler; does NOT commit (caller owns the
  transaction) unless commit=True is passed explicitly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import AdminAuditTrail
from app.auth.auth import require_role, get_current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Admin Panel"],
    dependencies=[Depends(require_role("admin"))],
)

# Valid enum values — documented here for frontend / OpenAPI consumers
VALID_ACTIONS = {
    "create", "update", "delete",
    "approve", "reject", "promote", "rollback",
}
VALID_ENTITY_TYPES = {
    "career", "cluster", "keyskill",
    "sme_profile", "sme_submission",
    "fit_band", "cps_factor", "aq",
    "weight_change_request",
    "weight_snapshot",
    "counsellor",
}


# ---------------------------------------------------------------------------
# Pydantic response schema
# ---------------------------------------------------------------------------

class AuditEntryOut(BaseModel):
    id:          int
    action:      str
    entity_type: str
    entity_id:   Optional[int]
    entity_name: Optional[str]
    user_id:     int
    user_email:  str
    details:     Optional[Dict[str, Any]]
    created_at:  datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# GET /audit-trail
# ---------------------------------------------------------------------------

@router.get(
    "/audit-trail",
    response_model=List[AuditEntryOut],
    summary="List admin audit trail entries (admin)",
)
def list_audit_trail(
    entity_type: Optional[str] = Query(None, description="Filter by entity_type"),
    action:      Optional[str] = Query(None, description="Filter by action"),
    user_email:  Optional[str] = Query(None, description="Filter by user_email (partial match)"),
    from_date:   Optional[datetime] = Query(None, description="Entries at or after this timestamp (ISO 8601)"),
    to_date:     Optional[datetime] = Query(None, description="Entries at or before this timestamp (ISO 8601)"),
    limit:       int = Query(100, ge=1, le=500, description="Max rows to return (default 100, max 500)"),
    db: Session = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = db.query(AdminAuditTrail)

    if entity_type:
        q = q.filter(AdminAuditTrail.entity_type == entity_type)
    if action:
        q = q.filter(AdminAuditTrail.action == action)
    if user_email:
        q = q.filter(AdminAuditTrail.user_email.ilike(f"%{user_email}%"))
    if from_date:
        q = q.filter(AdminAuditTrail.created_at >= from_date)
    if to_date:
        q = q.filter(AdminAuditTrail.created_at <= to_date)

    return q.order_by(AdminAuditTrail.created_at.desc()).limit(limit).all()


# ---------------------------------------------------------------------------
# 405 Method Not Allowed — append-only enforcement
# DELETE on the collection and on individual entries both return 405.
# ---------------------------------------------------------------------------

@router.delete(
    "/audit-trail",
    status_code=405,
    summary="Not allowed — audit trail is append-only",
    include_in_schema=False,
)
def delete_audit_trail_collection():
    raise HTTPException(
        status_code=405,
        detail="The audit trail is append-only. Deletion is not permitted.",
    )


@router.delete(
    "/audit-trail/{entry_id}",
    status_code=405,
    summary="Not allowed — audit trail is append-only",
    include_in_schema=False,
)
def delete_audit_trail_entry(entry_id: int):
    raise HTTPException(
        status_code=405,
        detail="The audit trail is append-only. Deletion is not permitted.",
    )


# ---------------------------------------------------------------------------
# log_audit helper — called by other admin endpoints
# ---------------------------------------------------------------------------

def log_audit(
    db:          Session,
    action:      str,
    entity_type: str,
    user_id:     int,
    user_email:  str,
    entity_id:   Optional[int] = None,
    entity_name: Optional[str] = None,
    details:     Optional[Dict[str, Any]] = None,
    commit:      bool = False,
) -> AdminAuditTrail:
    """
    Insert one audit trail row.

    Designed to be called inside an existing request handler:
      - Does NOT commit by default — the caller's db.commit() will flush it.
      - Pass commit=True only when the audit log is the last DB write in
        a handler that otherwise manages its own transaction.

    Never raises — any DB error is logged and swallowed so that a logging
    failure cannot break the primary operation.

    Returns the (potentially un-flushed) ORM row, or None on error.
    """
    try:
        entry = AdminAuditTrail(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            user_id=user_id,
            user_email=user_email,
            details=details,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        if commit:
            db.commit()
            db.refresh(entry)
        return entry
    except Exception as exc:
        logger.warning(
            "log_audit failed (action=%s entity_type=%s entity_id=%s): %s",
            action, entity_type, entity_id, exc,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return None
