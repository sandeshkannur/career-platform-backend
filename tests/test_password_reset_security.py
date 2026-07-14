"""
Tests for the password-reset security hardening fixes:

1. forgot-password/request no longer leaks identifier existence via a
   null-vs-populated expires_at — both branches now return the same
   response shape (see app/routers/password_reset.py forgot_password_request).
2. forgot-password/verify locks a reset token out after
   MAX_RESET_OTP_ATTEMPTS wrong-OTP attempts (429), even if the caller
   finally supplies the correct OTP on a later attempt.

Runs against an isolated in-memory SQLite instance, creating only the
tables this router touches (the full metadata has Postgres-only types
SQLite's compiler rejects, e.g. JSONB). No formal TestClient scaffold
exists yet for this router, so this sets one up directly.
"""
from __future__ import annotations

import os
from datetime import date

os.environ.setdefault("SKIP_DB_WAIT", "1")
os.environ.setdefault("SECRET_KEY", "dev-insecure-key")
os.environ["CP_EXPOSE_AUTH_SECRETS"] = "true"  # needed to read back dev.token/otp

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as appdb

_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)
appdb.engine = _test_engine
appdb.SessionLocal = _TestSessionLocal

import app.deps as appdeps

appdeps.SessionLocal = _TestSessionLocal

from fastapi.testclient import TestClient

from app.main import app
from app import models
from app.auth.auth import get_password_hash
from app.deps import get_db
from app.routers.password_reset import MAX_RESET_OTP_ATTEMPTS

models.Base.metadata.create_all(
    bind=_test_engine,
    tables=[models.User.__table__, models.PasswordResetLog.__table__],
)


def _override_get_db():
    db = _TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db

client = TestClient(app)


def _make_user(email: str, phone: str, password: str = "OldPass123") -> int:
    db = _TestSessionLocal()
    user = models.User(
        full_name="Test User",
        email=email,
        hashed_password=get_password_hash(password),
        dob=date(2000, 1, 1),
        is_minor=False,
        phone_number=phone,
        role="student",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    return user_id


def test_forgot_password_request_response_shape_matches_for_known_and_unknown():
    _make_user("known-user@example.com", "+911111111111")

    known = client.post(
        "/v1/auth/forgot-password/request",
        json={"channel": "email", "identifier": "known-user@example.com"},
    )
    unknown = client.post(
        "/v1/auth/forgot-password/request",
        json={"channel": "email", "identifier": "nobody-at-all@example.com"},
    )

    assert known.status_code == 200
    assert unknown.status_code == 200

    known_body = known.json()
    unknown_body = unknown.json()

    # Same message, same keys, both expires_at populated (non-null) — a
    # null-vs-populated expires_at was the leak this fix closes.
    assert known_body["message"] == unknown_body["message"]
    assert set(known_body.keys()) == set(unknown_body.keys())
    assert known_body["expires_at"] is not None
    assert unknown_body["expires_at"] is not None

    # dev payload legitimately differs (no real token exists for the
    # unknown identifier) — outside this fix's scope, and dev-only: never
    # returned in prod since CP_EXPOSE_AUTH_SECRETS must stay false there.
    assert known_body["dev"] is not None
    assert unknown_body["dev"] is None


def test_forgot_password_verify_locks_out_after_max_attempts():
    _make_user("attempts-user@example.com", "+922222222222")

    req = client.post(
        "/v1/auth/forgot-password/request",
        json={"channel": "email", "identifier": "attempts-user@example.com"},
    )
    dev = req.json()["dev"]
    token = dev["token"]
    correct_otp = dev["otp"]
    wrong_otp = "000000" if correct_otp != "000000" else "111111"

    # Exhaust the attempt cap with wrong OTPs.
    for _ in range(MAX_RESET_OTP_ATTEMPTS):
        r = client.post(
            "/v1/auth/forgot-password/verify",
            json={"token": token, "otp": wrong_otp, "new_password": "NewPass123"},
        )
        assert r.status_code == 400
        assert r.json()["detail"] == "Invalid OTP"

    # One more attempt, this time with the CORRECT OTP — still rejected,
    # because the cap is checked before the OTP itself is even compared.
    r = client.post(
        "/v1/auth/forgot-password/verify",
        json={"token": token, "otp": correct_otp, "new_password": "NewPass123"},
    )
    assert r.status_code == 429
