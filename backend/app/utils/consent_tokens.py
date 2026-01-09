# backend/app/utils/consent_tokens.py

from datetime import datetime, timezone
from typing import Any, Dict

from jose import jwt, JWTError


# =========================================================
# Exceptions (used by router)
# =========================================================

class ConsentTokenInvalid(Exception):
    """Raised when token is malformed or signature invalid."""


class ConsentTokenExpired(Exception):
    """Raised when token is valid but expired."""


class ConsentOtpInvalid(Exception):
    """Raised when OTP does not match."""


# =========================================================
# Helpers
# =========================================================

def require(payload: Dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise ConsentTokenInvalid(f"Missing claim: {key}")
    return payload[key]


def hash_otp_sha256(otp_plain: str) -> str:
    import hashlib
    return hashlib.sha256(otp_plain.encode("utf-8")).hexdigest()


# =========================================================
# Primary decode + validate (signature OK, manual exp check)
# =========================================================

def decode_and_validate_consent_token(
    token: str,
    secret_key: str,
    algorithm: str,
) -> Dict[str, Any]:
    """
    Decode and validate consent token.
    - Verifies signature
    - Ignores exp during decode
    - Enforces exp manually (time-bound)
    """

    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[algorithm],
            options={"verify_exp": False},  # IMPORTANT
        )
    except JWTError as e:
        raise ConsentTokenInvalid(str(e))

    # Required claims
    student_id = int(require(payload, "student_id"))
    student_user_id = int(require(payload, "student_user_id"))
    guardian_email = str(require(payload, "guardian_email"))
    otp_hash = str(require(payload, "otp_hash"))

    # Expiry enforcement (manual)
    exp_raw = require(payload, "exp")
    try:
        exp_ts = int(exp_raw)
    except Exception:
        raise ConsentTokenInvalid("Invalid exp claim")

    expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
    now = datetime.now(timezone.utc)

    if expires_at <= now:
        raise ConsentTokenExpired("Expired token")

    return {
        "student_id": student_id,
        "student_user_id": student_user_id,
        "guardian_email": guardian_email,
        "otp_hash": otp_hash,
        "expires_at": expires_at,
        "jti": payload.get("jti"),
        "raw": payload,
    }


# =========================================================
# Best-effort decode (for expired token logging)
# =========================================================

def decode_without_exp_verification(
    token: str,
    secret_key: str,
    algorithm: str,
) -> Dict[str, Any]:
    """
    Decode token ignoring exp, but still verifying signature.
    Used ONLY for audit logging of expired tokens.
    """
    try:
        return jwt.decode(
            token,
            secret_key,
            algorithms=[algorithm],
            options={"verify_exp": False},
        )
    except JWTError as e:
        raise ConsentTokenInvalid(str(e))


# =========================================================
# OTP verification
# =========================================================

def verify_otp_against_claim(otp_plain: str, otp_hash_claim: str) -> None:
    computed = hash_otp_sha256(otp_plain)
    if computed != (otp_hash_claim or ""):
        raise ConsentOtpInvalid("Invalid OTP")
