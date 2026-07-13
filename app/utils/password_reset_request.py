# backend/app/utils/password_reset_request.py
#
# Password reset request utilities:
# - Generate a 6-digit OTP
# - Hash OTP using SHA-256 (must match password_reset_tokens.py verification)
# - Create a self-contained password reset JWT
#
# IMPORTANT:
# - Do NOT store raw OTP or raw JWT in DB.
# - DB stores only metadata (jti, expires_at, user_id).
# - JWT includes otp_hash claim (not raw otp) and exp for server-side expiry enforcement.
# - Claims are {user_id, identifier, channel, otp_hash, exp, jti} — a distinct
#   shape from the consent token, so reset tokens can never be replayed
#   against the consent flow or vice versa.

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timezone
from typing import Dict

DEFAULT_RESET_TTL_SECONDS = 30 * 60  # 30 minutes


def generate_otp() -> str:
    """
    Returns a 6-digit numeric OTP as a zero-padded string.
    Example: "004219"
    """
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_sha256(otp_plain: str) -> str:
    """
    SHA-256 hash for OTP verification.
    Must match app/utils/password_reset_tokens.py verification logic.
    """
    return hashlib.sha256(otp_plain.encode("utf-8")).hexdigest()


def create_reset_token_jwt(
    *,
    user_id: int,
    identifier: str,
    channel: str,
    otp_hash: str,
    secret_key: str,
    algorithm: str,
    ttl_seconds: int = DEFAULT_RESET_TTL_SECONDS,
) -> Dict[str, object]:
    """
    Creates a self-contained password reset token (JWT).

    Claims align with decode_and_validate_reset_token():
    - user_id
    - identifier (email address or phone number, whichever channel matched)
    - channel ("email" | "mobile")
    - otp_hash (SHA-256 of OTP)
    - exp (unix timestamp)
    - jti (unique identifier used for audit correlation + replay guard)
    """
    now = int(time.time())
    exp = now + int(ttl_seconds)

    # Unique correlation ID for audit + idempotent lookups. Distinct prefix
    # from consent tokens ("consent-") so the two flows are never confused.
    jti = f"pwreset-{secrets.token_hex(8)}"

    from jose import jwt  # local import keeps dependency explicit

    payload = {
        "user_id": int(user_id),
        "identifier": str(identifier),
        "channel": str(channel),
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
