# backend/app/routers/consent.py
#
# Phase 1 (incremental) changes:
# ✅ POST /v1/consent/request  (student-only) - initiate guardian consent (DEV delivery stub)
# ✅ GET  /v1/consent/status   (student-only) - derived from consent_logs (read-only)
# ✅ POST /v1/consent/verify   (guardian JWT required) - self-contained token validation + audit logging
#
# Notes:
# - consent_verified is derived in /v1/auth/me (already done).
# - Email/SMS delivery is intentionally stubbed (prints token+otp to logs).
# - We keep existing verify behavior intact, but add production-grade idempotency.
#
# Option A (Playwright-friendly DEV mode):
# - When ENV=dev|test, /v1/consent/request also returns {dev: {token, otp}}
# - In prod, secrets are NEVER returned.

import os
import logging  # ✅ ADDED
from datetime import datetime, timezone, timedelta
from typing import Optional

from jose import jwt, JWTError  # ✅ ADDED
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_db
from app.auth.auth import get_current_active_user


from app.utils.consent_tokens import (
    ConsentTokenInvalid,
    ConsentTokenExpired,
    ConsentOtpInvalid,
    decode_and_validate_consent_token,
    decode_without_exp_verification,
    verify_otp_against_claim,
)

# IMPORTANT: reuse existing JWT settings (do not change B1–B12 auth behavior).
from app.auth.auth import SECRET_KEY, ALGORITHM


router = APIRouter(prefix="/consent", tags=["Consent"])

logger = logging.getLogger(__name__)  # ✅ ADDED


# -------------------------------------------------------------------
# Small helpers
# -------------------------------------------------------------------
def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _get_request_ip(req: Request) -> Optional[str]:
    # If behind proxy and you trust X-Forwarded-For, you can add it later.
    return req.client.host if req.client else None


# -------------------------------------------------------------------
# PHASE 1: Student consent request (student initiates)
# -------------------------------------------------------------------
@router.post(
    "/request",
    response_model=schemas.ConsentRequestResponse,
    status_code=status.HTTP_200_OK,
)
def request_consent(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Student initiates guardian consent request.

    Key behaviors:
    - Student-only
    - Minor-only
    - Idempotent: if an unexpired, unverified request exists, return it
    - Rate-limited: cooldown + hourly cap (DB-based, no Redis needed)
    - Stores ONLY metadata in DB (never raw OTP / never raw JWT)
    - Delivery stub prints token+otp to server logs (Phase 2 integrates provider)

    Option A (DEV/TEST only):
    - If ENV=dev|test, returns dev.token + dev.otp to make Playwright stable.
    - PROD NEVER returns secrets.
    """
    if getattr(current_user, "role", None) != "student":
        raise HTTPException(status_code=403, detail="Only students can request consent")

    if not getattr(current_user, "is_minor", False):
        raise HTTPException(status_code=400, detail="Consent not required for non-minors")

    guardian_email = getattr(current_user, "guardian_email", None)
    if not guardian_email:
        raise HTTPException(status_code=400, detail="Guardian email missing for minor")

    # Resolve Student.id (needed for logging + future reporting)
    student = (
        db.query(models.Student)
        .filter(models.Student.user_id == current_user.id)
        .first()
    )
    if not student:
        raise HTTPException(status_code=400, detail="Student profile not found for this user")

    now = _utcnow()
    ip = _get_request_ip(request)
    user_agent = request.headers.get("user-agent")

    # 1) Idempotency: reuse an unexpired, unverified consent request
    existing = (
        db.query(models.ConsentLog)
        .filter(
            models.ConsentLog.student_user_id == current_user.id,
            models.ConsentLog.verified_at.is_(None),
            models.ConsentLog.expires_at.isnot(None),
            models.ConsentLog.expires_at > now,
            models.ConsentLog.status == "sent",
        )
        .order_by(models.ConsentLog.created_at.desc())
        .first()
    )

    if existing:
        base = {
            "consent_id": existing.token_jti or "",
            "delivery": "email",
            "expires_at": existing.expires_at,
        }

        # DEV / TEST ONLY – required for Playwright stability
        # Note: OTP is not stored, so we mint a fresh OTP+token and update the log row.
        if (os.getenv("ENV") or "").strip().lower() in ("dev", "test"):
            from app.utils.consent_request import (
                generate_otp,
                hash_otp_sha256,
                create_consent_token_jwt,
            )

            otp_plain = generate_otp()
            otp_hash = hash_otp_sha256(otp_plain)

            token_bundle = create_consent_token_jwt(
                student_id=student.id,
                student_user_id=current_user.id,
                guardian_email=guardian_email,
                otp_hash=otp_hash,
                secret_key=SECRET_KEY,
                algorithm=ALGORITHM,
            )

            existing.token_jti = token_bundle["jti"]
            existing.expires_at = token_bundle["expires_at"]
            db.commit()

            base["dev"] = {
                "token": token_bundle["token"],
                "otp": otp_plain,
            }

        return base

    # 2) Rate limiting
    # 2a) Cooldown: prevent repeated clicks (1 per 60 seconds)
    last = (
        db.query(models.ConsentLog)
        .filter(models.ConsentLog.student_user_id == current_user.id)
        .order_by(models.ConsentLog.created_at.desc())
        .first()
    )
    if last and (now - last.created_at).total_seconds() < 60:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again shortly.")

    # 2b) Hourly cap: avoids abuse if user waits out cooldown repeatedly
    window_start = now - timedelta(hours=1)
    sent_last_hour = (
        db.query(models.ConsentLog)
        .filter(
            models.ConsentLog.student_user_id == current_user.id,
            models.ConsentLog.status == "sent",
            models.ConsentLog.created_at >= window_start,
        )
        .count()
    )
    if sent_last_hour >= 5:
        raise HTTPException(status_code=429, detail="Too many consent requests. Try again later.")

    # 3) Create OTP + consent token (JWT)
    from app.utils.consent_request import (
        generate_otp,
        hash_otp_sha256,
        create_consent_token_jwt,
    )

    otp_plain = generate_otp()
    otp_hash = hash_otp_sha256(otp_plain)

    token_bundle = create_consent_token_jwt(
        student_id=student.id,
        student_user_id=current_user.id,
        guardian_email=guardian_email,
        otp_hash=otp_hash,
        secret_key=SECRET_KEY,
        algorithm=ALGORITHM,
    )

    # 4) Persist "sent" audit row (NEVER store raw OTP / raw JWT)
    row = models.ConsentLog(
        student_id=student.id,
        student_user_id=current_user.id,
        guardian_email=guardian_email,
        token_jti=token_bundle["jti"],
        status="sent",
        reason=None,
        message=None,
        verified_at=None,
        expires_at=token_bundle["expires_at"],
        ip=ip,
        user_agent=user_agent,
        created_at=now,  # explicit for clarity (DB default also OK)
    )
    db.add(row)
    db.commit()

    # 5) Delivery stub (DEV ONLY)
    # In Phase 2, replace this with email/SMS provider integration.
    print("=== CONSENT REQUEST (DEV STUB) ===")
    print("guardian_email:", guardian_email)
    print("consent_token:", token_bundle["token"])
    print("otp:", otp_plain)
    print("expires_at:", token_bundle["expires_at"].isoformat())
    print("=================================")

    # -------------------------------------------------------------------
    # Option A: DEV / TEST ONLY - expose token + OTP for Playwright automation
    # -------------------------------------------------------------------
    # SECURITY NOTE:
    # - "dev" payload is returned ONLY when ENV=dev|test.
    # - Never enable this in prod; OTP/JWT are secrets.

    #print("CONSENT_REQUEST ENV =", repr(os.getenv("ENV")))
    if (os.getenv("ENV") or "").strip().lower() in ("dev", "test"):
        return {
            "consent_id": token_bundle["jti"],
            "delivery": "email",
            "expires_at": token_bundle["expires_at"],
            "dev": {
                "token": token_bundle["token"],
                "otp": otp_plain,
            },
        }

    return schemas.ConsentRequestResponse(
        consent_id=token_bundle["jti"],
        delivery="email",
        expires_at=token_bundle["expires_at"],
    )


# -------------------------------------------------------------------
# PHASE 1: Student consent status (read-only)
# -------------------------------------------------------------------
@router.get("/status", status_code=status.HTTP_200_OK)
def get_consent_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Student-only endpoint that returns current consent state.

    Contract:
    {
      "state": "idle | sent | verified | expired",
      "expires_at": "..." | null
    }

    Derived from consent_logs (read-only).
    """
    if getattr(current_user, "role", None) != "student":
        raise HTTPException(status_code=403, detail="Only students can view consent status")

    # Non-minors do not require consent.
    if not getattr(current_user, "is_minor", False):
        return {"state": "idle", "expires_at": None}

    latest = (
        db.query(models.ConsentLog)
        .filter(models.ConsentLog.student_user_id == current_user.id)
        .order_by(models.ConsentLog.created_at.desc())
        .first()
    )

    if not latest:
        return {"state": "idle", "expires_at": None}

    if latest.verified_at is not None:
        return {"state": "verified", "expires_at": latest.expires_at}

    if latest.expires_at is not None and latest.expires_at <= _utcnow():
        return {"state": "expired", "expires_at": latest.expires_at}

    return {"state": "sent", "expires_at": latest.expires_at}


# -------------------------------------------------------------------
# B13: Guardian consent verification (existing behavior + idempotency)
# -------------------------------------------------------------------
@router.post(
    "/verify",
    response_model=schemas.ConsentVerifyResponse,
    status_code=status.HTTP_200_OK,
)
def verify_consent(
    payload: schemas.ConsentVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Guardian verifies parental consent.

    Existing rules:
    - JWT required (guardian must be logged-in)
    - Consent token validation must NOT depend on DB (self-contained JWT)
    - Log every attempt to consent_logs (write-only auditing)

    Production polish added:
    - Idempotency: if token_jti already verified -> 409 Conflict (and audited)
    """
    verified_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    ip = _get_request_ip(request)
    user_agent = request.headers.get("user-agent")

    # Safe defaults for logging if token is invalid
    student_id_for_log = -1
    student_user_id_for_log = -1
    guardian_email_for_log = "unknown"
    token_jti_for_log = None

    # ✅ ADDED: Pre-decode debug (does NOT accept the token, only logs why decode fails)
    try:
        _dbg = jwt.decode(payload.token, SECRET_KEY, algorithms=[ALGORITHM])
        logger.info(
            "Consent verify debug decode OK: jti=%s student_id=%s student_user_id=%s guardian_email=%s",
            _dbg.get("jti"),
            _dbg.get("student_id"),
            _dbg.get("student_user_id"),
            _dbg.get("guardian_email"),
        )
    except JWTError as e:
        logger.exception("Consent verify debug decode FAILED: %s", str(e))

    try:
        # 1) Decode + validate JWT signature + exp
        claims = decode_and_validate_consent_token(
            token=payload.token,
            secret_key=SECRET_KEY,
            algorithm=ALGORITHM,
        )

        student_id_for_log = claims["student_id"]
        student_user_id_for_log = claims["student_user_id"]
        guardian_email_for_log = str(claims["guardian_email"]).strip().lower()
        token_jti_for_log = claims.get("jti")
        expires_at = claims["expires_at"]

        # 3) Idempotency: already verified for this token_jti?
        if token_jti_for_log:
            already_verified = (
                db.query(models.ConsentLog)
                .filter(
                    models.ConsentLog.student_user_id == student_user_id_for_log,
                    models.ConsentLog.token_jti == token_jti_for_log,
                    models.ConsentLog.verified_at.isnot(None),
                )
                .first()
            )
            if already_verified:
                _write_consent_log(
                    db=db,
                    student_id=student_id_for_log,
                    student_user_id=student_user_id_for_log,
                    guardian_email=guardian_email_for_log,
                    token_jti=token_jti_for_log,
                    status="rejected",
                    reason="already_verified",
                    message="Already verified",
                    verified_at=None,
                    expires_at=expires_at,
                    ip=ip,
                    user_agent=user_agent,
                )
                raise HTTPException(status_code=409, detail="Already verified")

        # 4) OTP check (400)
        verify_otp_against_claim(payload.otp, claims["otp_hash"])

        # ✅ Verified
        verified_at = _utcnow()
        _write_consent_log(
            db=db,
            student_id=student_id_for_log,
            student_user_id=student_user_id_for_log,
            guardian_email=guardian_email_for_log,
            token_jti=token_jti_for_log,
            status="verified",
            reason=None,
            message=None,
            verified_at=verified_at,
            expires_at=expires_at,
            ip=ip,
            user_agent=user_agent,
        )

        return schemas.ConsentVerifyResponse(
            verified=True,
            status="verified",
            message=None,
            student_id=claims["student_id"],
            student_user_id=claims["student_user_id"],
            guardian_email=claims["guardian_email"],
            verified_at=verified_at,
            expires_at=claims["expires_at"],
        )

    except ConsentTokenExpired:
        # Expired token => best-effort claim extraction for consistent logs
        reason = "expired_token"
        message = "Expired token"
        try:
            p = decode_without_exp_verification(payload.token, SECRET_KEY, ALGORITHM)
            student_id_for_log = int(p.get("student_id", student_id_for_log))
            student_user_id_for_log = int(p.get("student_user_id", student_user_id_for_log))
            guardian_email_for_log = str(p.get("guardian_email", guardian_email_for_log)).strip().lower()
            token_jti_for_log = p.get("jti")
            exp_raw = p.get("exp")
            if exp_raw is not None:
                expires_at = datetime.fromtimestamp(int(exp_raw), tz=timezone.utc)
        except Exception:
            pass

        _write_consent_log(
            db=db,
            student_id=student_id_for_log,
            student_user_id=student_user_id_for_log,
            guardian_email=guardian_email_for_log,
            token_jti=token_jti_for_log,
            status="rejected",
            reason=reason,
            message=message,
            verified_at=None,
            expires_at=expires_at,
            ip=ip,
            user_agent=user_agent,
        )
        raise HTTPException(status_code=400, detail=message)

    except ConsentOtpInvalid:
        _write_consent_log(
            db=db,
            student_id=student_id_for_log,
            student_user_id=student_user_id_for_log,
            guardian_email=guardian_email_for_log,
            token_jti=token_jti_for_log,
            status="rejected",
            reason="invalid_otp",
            message="Invalid OTP",
            verified_at=None,
            expires_at=expires_at,
            ip=ip,
            user_agent=user_agent,
        )
        raise HTTPException(status_code=400, detail="Invalid OTP")

    except ConsentTokenInvalid:
        _write_consent_log(
            db=db,
            student_id=student_id_for_log,
            student_user_id=student_user_id_for_log,
            guardian_email=guardian_email_for_log,
            token_jti=token_jti_for_log,
            status="rejected",
            reason="invalid_token",
            message="Invalid token",
            verified_at=None,
            expires_at=None,
            ip=ip,
            user_agent=user_agent,
        )
        raise HTTPException(status_code=400, detail="Invalid token")


# -------------------------------------------------------------------
# Internal: write-only audit log
# -------------------------------------------------------------------
def _write_consent_log(
    db: Session,
    student_id: int,
    student_user_id: int,
    guardian_email: str,
    token_jti: Optional[str],
    status: str,
    reason: Optional[str],
    message: Optional[str],
    verified_at: Optional[datetime],
    expires_at: Optional[datetime],
    ip: Optional[str],
    user_agent: Optional[str],
) -> None:
    """
    Writes an audit log row to consent_logs.

    Must remain "write-only" (does not query DB), so audit writes are deterministic
    and never affect auth/session correctness.
    """
    row = models.ConsentLog(
        student_id=student_id,
        student_user_id=student_user_id,
        guardian_email=guardian_email,
        token_jti=token_jti,
        status=status,
        reason=reason,
        message=message,
        verified_at=verified_at,
        expires_at=expires_at,
        ip=ip,
        user_agent=user_agent,
    )
    db.add(row)
    db.commit()
