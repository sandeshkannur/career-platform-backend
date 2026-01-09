# backend/app/utils/consent_request.py
#
# Phase 1 consent request utilities:
# - Generate a 6-digit OTP
# - Hash OTP using SHA-256 (must match consent_tokens.py verification)
# - Create a self-contained consent JWT for guardian verification
#
# IMPORTANT:
# - Do NOT store raw OTP or raw JWT in DB.
# - DB stores only metadata (jti, expires_at, guardian_email, student ids).
# - JWT includes otp_hash claim (not raw otp) and exp for server-side expiry enforcement.

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timezone
from typing import Dict

DEFAULT_CONSENT_TTL_SECONDS = 30 * 60  # 30 minutes


def generate_otp() -> str:
    """
    Returns a 6-digit numeric OTP as a zero-padded string.
    Example: "004219"
    """
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_sha256(otp_plain: str) -> str:
    """
    SHA-256 hash for OTP verification.
    Must match app/utils/consent_tokens.py verification logic.
    """
    return hashlib.sha256(otp_plain.encode("utf-8")).hexdigest()


def create_consent_token_jwt(
    *,
    student_id: int,
    student_user_id: int,
    guardian_email: str,
    otp_hash: str,
    secret_key: str,
    algorithm: str,
    ttl_seconds: int = DEFAULT_CONSENT_TTL_SECONDS,
) -> Dict[str, object]:
    """
    Creates a self-contained consent token (JWT) for guardian verification.

    Claims align with decode_and_validate_consent_token():
    - student_id
    - student_user_id
    - guardian_email
    - otp_hash (SHA-256 of OTP)
    - exp (unix timestamp)
    - jti (unique identifier used as consent_id + audit correlation id)
    """
    now = int(time.time())
    exp = now + int(ttl_seconds)

    # Unique correlation ID for audit + idempotent lookups
    jti = f"consent-{secrets.token_hex(8)}"

    from jose import jwt  # local import keeps dependency explicit

    payload = {
        "student_id": int(student_id),
        "student_user_id": int(student_user_id),
        "guardian_email": str(guardian_email),
        "otp_hash": str(otp_hash),
        "exp": exp,
        "jti": jti,
    }

    token = jwt.encode(payload, secret_key, algorithm=algorithm)

    return {
        "token": token,
        "jti": jti,
        "expires_at": datetime.fromtimestamp(exp, tz=timezone.utc),
    }
