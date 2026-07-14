"""
Admin password-reset controls.

Endpoints (all admin-only, mounted under /v1/admin):
  POST /users/{user_id}/reset-password/trigger — send the user the same
       OTP+token reset flow as the public forgot-password/request endpoint.
       The admin never sees the OTP or token — only that it was sent.
  POST /users/{user_id}/reset-password/direct  — admin sets a specific
       password immediately, no OTP. Reserved for cases where the user
       genuinely cannot receive email/SMS (see docstring below).
  GET  /password-reset-logs — paginated, filterable read-only view over
       password_reset_logs, joined with user/admin email for readability.

Conventions:
  - Both mutating endpoints reuse app.routers.password_reset's helpers
    (_issue_reset_otp, _write_password_reset_log) rather than duplicating
    OTP/token/notifier logic — one code path for "issue a reset," shared
    with the public self-service flow.
  - Every action is tagged method='admin_reset' with initiated_by_admin_id
    set, on top of whatever else password_reset_logs already tracks.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, aliased

from app import models, schemas
from app.deps import get_db
from app.auth.auth import require_role, get_password_hash
from app.routers.password_reset import (
    _get_request_ip,
    _write_password_reset_log,
    _issue_reset_otp,
)

router = APIRouter(
    tags=["Admin Panel"],
    dependencies=[Depends(require_role("admin"))],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user_or_404(db: Session, user_id: int) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {user_id}",
        )
    return user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/users/{user_id}/reset-password/trigger",
    status_code=status.HTTP_200_OK,
    summary="Send a user the OTP password-reset flow (admin)",
)
def admin_trigger_password_reset(
    user_id: int,
    payload: schemas.AdminResetPasswordTriggerRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_role("admin")),
):
    """
    Issues the same OTP+reset-token flow as the public
    forgot-password/request endpoint, via the shared _issue_reset_otp()
    helper — but tagged method='admin_reset' with initiated_by_admin_id
    set, and unlike the public endpoint, this response NEVER includes the
    OTP or token, regardless of CP_EXPOSE_AUTH_SECRETS. An admin who could
    read the OTP back would defeat the "admin never learns the password"
    property this endpoint exists to preserve — the user must still
    complete the flow themselves via forgot-password/verify.
    """
    user = _get_user_or_404(db, user_id)

    if payload.channel == "mobile" and not user.phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no phone number on file",
        )

    ip = _get_request_ip(request)
    user_agent = request.headers.get("user-agent")

    _issue_reset_otp(
        db=db,
        user=user,
        channel=payload.channel,
        ip=ip,
        user_agent=user_agent,
        method="admin_reset",
        initiated_by_admin_id=current_admin.id,
    )

    return {
        "success": True,
        "message": f"Reset instructions sent to the user's {payload.channel}.",
    }


@router.post(
    "/users/{user_id}/reset-password/direct",
    status_code=status.HTTP_200_OK,
    summary="Set a user's password directly, no OTP (admin)",
)
def admin_direct_set_password(
    user_id: int,
    payload: schemas.AdminResetPasswordDirectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_role("admin")),
):
    """
    Sets a user's password immediately to an admin-supplied value, with NO
    OTP step.

    WARNING: this bypasses the OTP verification flow entirely and is a
    broader-trust operation than /trigger — the admin directly sets (and
    therefore knows) the new password. Reserve this for cases where the
    user genuinely cannot receive email/SMS (e.g. a support escalation);
    prefer /trigger whenever the user can complete the OTP flow themselves.
    """
    user = _get_user_or_404(db, user_id)

    ip = _get_request_ip(request)
    user_agent = request.headers.get("user-agent")

    user.hashed_password = get_password_hash(payload.new_password)
    db.commit()

    _write_password_reset_log(
        db=db,
        user_id=user.id,
        method="admin_reset",
        status="completed",
        reason="direct_set_by_admin",
        token_jti=None,
        ip=ip,
        user_agent=user_agent,
        initiated_by_admin_id=current_admin.id,
    )

    return {"success": True}


@router.get(
    "/password-reset-logs",
    response_model=schemas.PasswordResetLogListResponse,
    summary="Paginated password-reset audit log (admin)",
)
def list_password_reset_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user_id: Optional[int] = Query(None, description="Filter by the affected user's id"),
    method: Optional[str] = Query(None, description="Filter by method, e.g. 'admin_reset'"),
    status_: Optional[str] = Query(None, alias="status", description="Filter by status, e.g. 'completed'"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_role("admin")),
):
    InitiatorUser = aliased(models.User)

    q = (
        db.query(
            models.PasswordResetLog,
            models.User.email.label("user_email"),
            InitiatorUser.email.label("initiated_by_admin_email"),
        )
        .outerjoin(models.User, models.User.id == models.PasswordResetLog.user_id)
        .outerjoin(InitiatorUser, InitiatorUser.id == models.PasswordResetLog.initiated_by_admin_id)
    )

    if user_id is not None:
        q = q.filter(models.PasswordResetLog.user_id == user_id)
    if method is not None:
        q = q.filter(models.PasswordResetLog.method == method)
    if status_ is not None:
        q = q.filter(models.PasswordResetLog.status == status_)

    total = q.count()

    rows = (
        q.order_by(models.PasswordResetLog.created_at.desc(), models.PasswordResetLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [
        schemas.PasswordResetLogEntry(
            id=log.id,
            user_id=log.user_id,
            user_email=user_email,
            method=log.method,
            status=log.status,
            reason=log.reason,
            initiated_by_admin_id=log.initiated_by_admin_id,
            initiated_by_admin_email=initiated_by_admin_email,
            token_jti=log.token_jti,
            ip=log.ip,
            user_agent=log.user_agent,
            created_at=log.created_at,
        )
        for log, user_email, initiated_by_admin_email in rows
    ]

    return schemas.PasswordResetLogListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
