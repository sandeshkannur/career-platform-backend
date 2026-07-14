# backend/app/routers/password_reset.py
#
# Password reset module:
# - POST /v1/auth/change-password          (authenticated self-service)
# - POST /v1/auth/forgot-password/request  (public, email or mobile channel)
# - POST /v1/auth/forgot-password/verify   (public, token+OTP -> new password)
#
# Mirrors app/routers/consent.py's patterns:
# - Self-contained JWT + SHA-256 OTP hash (app/utils/password_reset_tokens.py,
#   app/utils/password_reset_request.py) — token validation never reads the DB.
# - Every attempt (success or failure) is written to password_reset_logs
#   (write-only audit trail), mirroring _write_consent_log's usage in
#   app/routers/consent.py.
# - Delivery goes through app.services.notifications.factory: get_notifier()
#   for email (CP_NOTIFIER; defaults to logging only), get_sms_notifier()
#   for mobile (CP_SMS_NOTIFIER; only LogSmsNotifier exists today).
# - Option A (Playwright-friendly DEV mode): when CP_EXPOSE_AUTH_SECRETS=true,
#   /v1/auth/forgot-password/request also returns {dev: {token, otp}}. In
#   prod this must stay false — never returns secrets.
#
# IMPORTANT: reset tokens use a distinct claims shape/jti prefix ("pwreset-")
# from consent tokens ("consent-") so the two flows can never be replayed
# against each other.

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_db
from app.auth.auth import (
    get_current_active_user,
    get_password_hash,
    verify_password,
    expose_auth_secrets,
    SECRET_KEY,
    ALGORITHM,
)
from app.services.notifications.factory import get_notifier, get_sms_notifier
from app.services.notifications.locales import DEFAULT_LOCALE

from app.utils.password_reset_tokens import (
    ResetTokenInvalid,
    ResetTokenExpired,
    ResetOtpInvalid,
    decode_and_validate_reset_token,
    decode_without_exp_verification,
    verify_otp_against_claim,
)
from app.utils.password_reset_request import (
    generate_otp,
    hash_otp_sha256,
    create_reset_token_jwt,
    DEFAULT_RESET_TTL_SECONDS,
)

router = APIRouter(prefix="/auth", tags=["Password Reset"])

logger = logging.getLogger(__name__)

# Max wrong-OTP attempts allowed against a single reset token (token_jti)
# before it is locked out, mirroring LoginOtp's attempts>=5 cap in
# app/auth/auth.py's verify_login_otp(). Counted from password_reset_logs
# rows rather than a mutable counter column, since every attempt is already
# written there (status='rejected', reason='invalid_otp') — see
# forgot_password_verify() below.
MAX_RESET_OTP_ATTEMPTS = 5


# -------------------------------------------------------------------
# Small helpers
# -------------------------------------------------------------------
def _get_request_ip(req: Request) -> Optional[str]:
    return req.client.host if req.client else None


def _write_password_reset_log(
    db: Session,
    user_id: Optional[int],
    method: str,
    status: str,
    reason: Optional[str],
    token_jti: Optional[str],
    ip: Optional[str],
    user_agent: Optional[str],
    initiated_by_admin_id: Optional[int] = None,
) -> None:
    """
    Writes an audit log row to password_reset_logs. Write-only, mirroring
    _write_consent_log in app/routers/consent.py.
    """
    row = models.PasswordResetLog(
        user_id=user_id,
        method=method,
        status=status,
        reason=reason,
        initiated_by_admin_id=initiated_by_admin_id,
        token_jti=token_jti,
        ip=ip,
        user_agent=user_agent,
    )
    db.add(row)
    db.commit()


def _issue_reset_otp(
    db: Session,
    user: models.User,
    channel: str,
    ip: Optional[str],
    user_agent: Optional[str],
    method: str,
    initiated_by_admin_id: Optional[int] = None,
) -> dict:
    """
    Generates an OTP + reset token for `user`, writes the 'otp_sent' audit
    row, and dispatches it via the configured notifier for `channel`.

    Shared by forgot_password_request() (public, self-service) and the
    admin "trigger" endpoint (app/routers/admin/password_reset_admin.py) —
    one code path for "create a reset token+OTP and send it," so the two
    callers can never drift apart on how a reset is actually issued. Only
    the audit `method` (and, for admin-initiated resets,
    `initiated_by_admin_id`) differs between callers; what the caller does
    with the returned token/otp (e.g. whether to ever surface them back to
    the caller) is entirely up to the caller.

    Returns {"token_bundle": {...}, "otp_plain": str} — token_bundle is
    create_reset_token_jwt()'s return value (token, jti, expires_at).
    """
    otp_plain = generate_otp()
    otp_hash = hash_otp_sha256(otp_plain)

    identifier = user.email if channel == "email" else user.phone_number

    token_bundle = create_reset_token_jwt(
        user_id=user.id,
        identifier=identifier,
        channel=channel,
        otp_hash=otp_hash,
        secret_key=SECRET_KEY,
        algorithm=ALGORITHM,
    )

    _write_password_reset_log(
        db=db,
        user_id=user.id,
        method=method,
        status="otp_sent",
        reason=None,
        token_jti=token_bundle["jti"],
        ip=ip,
        user_agent=user_agent,
        initiated_by_admin_id=initiated_by_admin_id,
    )

    # Delivery is best-effort: the audit row above is already committed, and
    # this call must succeed regardless of delivery outcome, even if a
    # notifier implementation violates its own never-raise contract.
    try:
        if channel == "email":
            frontend_base_url = (os.getenv("CP_FRONTEND_BASE_URL") or "https://mapyourcareer.in").rstrip("/")
            reset_url = f"{frontend_base_url}/reset-password?token={token_bundle['token']}"

            get_notifier().send(
                to=user.email,
                template="password_reset",
                context={
                    "user_name": user.full_name,
                    "otp": otp_plain,
                    "reset_url": reset_url,
                },
                locale=DEFAULT_LOCALE,
            )
        else:
            get_sms_notifier().send(
                to_number=user.phone_number,
                message=(
                    f"Your MapYourCareer password reset code is {otp_plain}. "
                    "It expires in 30 minutes. If you did not request this, ignore this message."
                ),
            )
    except Exception:
        logger.exception(
            "Notifier raised despite the never-raise contract; reset-OTP "
            "issuance still succeeds. user_id=%s reset_id=%s method=%s",
            user.id,
            token_bundle["jti"],
            method,
        )

    return {"token_bundle": token_bundle, "otp_plain": otp_plain}


# -------------------------------------------------------------------
# Authenticated self-service: change password
# -------------------------------------------------------------------
@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    payload: schemas.ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Authenticated user changes their own password.

    - Verifies current_password against the stored hash (401 on mismatch)
    - new_password policy: min_length=8 (schemas.ChangePasswordRequest),
      the same bound already enforced for admin-created counsellor accounts
      (app/routers/admin/counsellors.py CounsellorCreate.password) — public
      signup (schemas.UserCreate.password) enforces no policy at all, so
      that bound is not a usable precedent here.
    """
    ip = _get_request_ip(request)
    user_agent = request.headers.get("user-agent")

    if not verify_password(payload.current_password, current_user.hashed_password):
        _write_password_reset_log(
            db=db,
            user_id=current_user.id,
            method="self_change",
            status="failed",
            reason="invalid_current_password",
            token_jti=None,
            ip=ip,
            user_agent=user_agent,
        )
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    current_user.hashed_password = get_password_hash(payload.new_password)
    db.commit()

    _write_password_reset_log(
        db=db,
        user_id=current_user.id,
        method="self_change",
        status="completed",
        reason=None,
        token_jti=None,
        ip=ip,
        user_agent=user_agent,
    )

    return {"success": True}


# -------------------------------------------------------------------
# Public: forgot-password request (email or mobile channel)
# -------------------------------------------------------------------
@router.post(
    "/forgot-password/request",
    response_model=schemas.ForgotPasswordRequestResponse,
    status_code=status.HTTP_200_OK,
)
def forgot_password_request(
    payload: schemas.ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public endpoint. Never reveals whether the identifier (email/phone)
    belongs to an account — always returns the same generic message.

    - identifier found: generates OTP + reset token (30 min TTL), logs
      status='otp_sent', dispatches via the configured notifier for the
      requested channel.
    - identifier not found: logs status='rejected' reason='identifier_not_found'
      (user_id=None) for abuse investigation, but still returns success.
    """
    ip = _get_request_ip(request)
    user_agent = request.headers.get("user-agent")

    generic_message = "If an account exists, reset instructions were sent."
    identifier_raw = (payload.identifier or "").strip()

    if payload.channel == "email":
        identifier = identifier_raw.lower()
        user = db.query(models.User).filter(models.User.email == identifier).first()
        method = "forgot_email"
    else:
        identifier = identifier_raw
        user = db.query(models.User).filter(models.User.phone_number == identifier).first()
        method = "forgot_mobile"

    # TIMING SIDE-CHANNEL (documented, not fixed here): the found-user branch
    # below does real work before returning — OTP generation, JWT signing,
    # a DB write, and a notifier dispatch — while the not-found branch below
    # returns almost immediately. That gap is a measurable timing signal an
    # attacker could use to enumerate valid identifiers at scale, even though
    # the response bodies are now identical (see the expires_at fix above).
    # Accepted as low-priority given current beta traffic volume; flagged for
    # future hardening (e.g. constant-time delay padding on this endpoint).
    if not user:
        _write_password_reset_log(
            db=db,
            user_id=None,
            method=method,
            status="rejected",
            reason="identifier_not_found",
            token_jti=None,
            ip=ip,
            user_agent=user_agent,
        )
        # Synthetic expires_at (no real token/DB row backs it) so this
        # response is shape-identical to the found-user branch — a null
        # expires_at here vs. a populated one for known identifiers was
        # itself a distinguishing signal that broke the "never reveal
        # whether the identifier exists" guarantee. Reuses the same TTL
        # constant create_reset_token_jwt() defaults to, so the two branches
        # can never silently drift apart.
        synthetic_expires_at = datetime.now(timezone.utc) + timedelta(seconds=DEFAULT_RESET_TTL_SECONDS)
        return schemas.ForgotPasswordRequestResponse(
            message=generic_message,
            expires_at=synthetic_expires_at,
        )

    issued = _issue_reset_otp(
        db=db,
        user=user,
        channel=payload.channel,
        ip=ip,
        user_agent=user_agent,
        method=method,
    )
    token_bundle = issued["token_bundle"]
    otp_plain = issued["otp_plain"]

    if expose_auth_secrets():
        return schemas.ForgotPasswordRequestResponse(
            message=generic_message,
            expires_at=token_bundle["expires_at"],
            dev=schemas.PasswordResetDevPayload(token=token_bundle["token"], otp=otp_plain),
        )

    return schemas.ForgotPasswordRequestResponse(
        message=generic_message,
        expires_at=token_bundle["expires_at"],
    )


# -------------------------------------------------------------------
# Public: forgot-password verify (token + OTP -> new password)
# -------------------------------------------------------------------
@router.post("/forgot-password/verify", status_code=status.HTTP_200_OK)
def forgot_password_verify(
    payload: schemas.ForgotPasswordVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Decodes/validates the reset token (self-contained JWT, DB never
    consulted for validity), checks the OTP, and — on success — updates the
    password. Every branch (success or failure) writes a password_reset_logs
    row, mirroring verify_consent's exception handling in consent.py.
    """
    ip = _get_request_ip(request)
    user_agent = request.headers.get("user-agent")

    user_id_for_log: Optional[int] = None
    token_jti_for_log: Optional[str] = None
    method_for_log = "forgot_email"

    try:
        claims = decode_and_validate_reset_token(
            token=payload.token,
            secret_key=SECRET_KEY,
            algorithm=ALGORITHM,
        )

        user_id_for_log = claims["user_id"]
        token_jti_for_log = claims.get("jti")
        method_for_log = "forgot_email" if claims["channel"] == "email" else "forgot_mobile"

        # Idempotency: reject replay of an already-completed token
        if token_jti_for_log:
            already_completed = (
                db.query(models.PasswordResetLog)
                .filter(
                    models.PasswordResetLog.user_id == user_id_for_log,
                    models.PasswordResetLog.token_jti == token_jti_for_log,
                    models.PasswordResetLog.status == "completed",
                )
                .first()
            )
            if already_completed:
                _write_password_reset_log(
                    db=db,
                    user_id=user_id_for_log,
                    method=method_for_log,
                    status="rejected",
                    reason="already_verified",
                    token_jti=token_jti_for_log,
                    ip=ip,
                    user_agent=user_agent,
                )
                raise HTTPException(status_code=409, detail="Already verified")

        # Attempt cap: count prior wrong-OTP tries logged against this exact
        # token_jti (each one already wrote a status='rejected'
        # reason='invalid_otp' row below on failure — that write is itself
        # the counter, so no separate mutable attempts column is needed).
        # token_jti is indexed, so this is a cheap, indexed COUNT. Checked
        # BEFORE verify_otp_against_claim() so a token that has already
        # exhausted its attempts stays locked out even if the caller finally
        # supplies the correct OTP.
        if token_jti_for_log:
            prior_failed_attempts = (
                db.query(models.PasswordResetLog)
                .filter(
                    models.PasswordResetLog.token_jti == token_jti_for_log,
                    models.PasswordResetLog.status == "rejected",
                    models.PasswordResetLog.reason == "invalid_otp",
                )
                .count()
            )
            if prior_failed_attempts >= MAX_RESET_OTP_ATTEMPTS:
                _write_password_reset_log(
                    db=db,
                    user_id=user_id_for_log,
                    method=method_for_log,
                    status="rejected",
                    reason="max_attempts_exceeded",
                    token_jti=token_jti_for_log,
                    ip=ip,
                    user_agent=user_agent,
                )
                raise HTTPException(status_code=429, detail="Too many failed attempts. Request a new reset link.")

        verify_otp_against_claim(payload.otp, claims["otp_hash"])

        user = db.query(models.User).filter(models.User.id == user_id_for_log).first()
        if not user:
            _write_password_reset_log(
                db=db,
                user_id=user_id_for_log,
                method=method_for_log,
                status="failed",
                reason="user_not_found",
                token_jti=token_jti_for_log,
                ip=ip,
                user_agent=user_agent,
            )
            raise HTTPException(status_code=400, detail="Invalid token")

        user.hashed_password = get_password_hash(payload.new_password)
        db.commit()

        _write_password_reset_log(
            db=db,
            user_id=user_id_for_log,
            method=method_for_log,
            status="completed",
            reason=None,
            token_jti=token_jti_for_log,
            ip=ip,
            user_agent=user_agent,
        )

        return {"success": True}

    except ResetTokenExpired:
        try:
            p = decode_without_exp_verification(payload.token, SECRET_KEY, ALGORITHM)
            raw_user_id = p.get("user_id")
            user_id_for_log = int(raw_user_id) if raw_user_id is not None else None
            token_jti_for_log = p.get("jti")
            method_for_log = "forgot_email" if p.get("channel") == "email" else "forgot_mobile"
        except Exception:
            pass

        _write_password_reset_log(
            db=db,
            user_id=user_id_for_log,
            method=method_for_log,
            status="rejected",
            reason="expired_token",
            token_jti=token_jti_for_log,
            ip=ip,
            user_agent=user_agent,
        )
        raise HTTPException(status_code=400, detail="Expired token")

    except ResetOtpInvalid:
        _write_password_reset_log(
            db=db,
            user_id=user_id_for_log,
            method=method_for_log,
            status="rejected",
            reason="invalid_otp",
            token_jti=token_jti_for_log,
            ip=ip,
            user_agent=user_agent,
        )
        raise HTTPException(status_code=400, detail="Invalid OTP")

    except ResetTokenInvalid:
        _write_password_reset_log(
            db=db,
            user_id=user_id_for_log,
            method=method_for_log,
            status="rejected",
            reason="invalid_token",
            token_jti=token_jti_for_log,
            ip=ip,
            user_agent=user_agent,
        )
        raise HTTPException(status_code=400, detail="Invalid token")
