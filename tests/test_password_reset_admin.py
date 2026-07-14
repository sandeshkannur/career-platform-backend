"""
Tests for the admin password-reset controls
(app/routers/admin/password_reset_admin.py):

1. /trigger never returns the OTP or reset token in its response body,
   regardless of CP_EXPOSE_AUTH_SECRETS (unlike the public
   forgot-password/request endpoint, which does expose them when that
   flag is set — an admin being able to read the OTP back would defeat
   the "admin never learns the password" property /trigger exists for).
2. /direct actually changes the target user's password (old password stops
   working, new one works) with no OTP step involved.
3. GET /password-reset-logs requires admin auth (403 for a student token)
   and returns correctly paginated/filtered results.

Uses its own isolated FastAPI app instance (via app.main.create_app()),
deliberately NOT reusing the shared app.main.app singleton that
tests/test_password_reset_security.py overrides — two test modules
overriding get_db on the same shared app instance at import time would
race (whichever module is collected last wins for both, silently pointing
one file's requests at the other file's in-memory database). A fresh
app instance gets its own independent dependency_overrides.
"""
from __future__ import annotations

import os
from datetime import date

os.environ.setdefault("SKIP_DB_WAIT", "1")
os.environ.setdefault("SECRET_KEY", "dev-insecure-key")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fastapi.testclient import TestClient

from app.main import create_app
from app import models
from app.auth.auth import get_password_hash
from app.deps import get_db

_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

# Only the tables this module's endpoints touch — the full metadata has
# Postgres-only types (JSONB) that SQLite's compiler rejects.
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


app = create_app()
app.dependency_overrides[get_db] = _override_get_db

client = TestClient(app)


def _make_user(email: str, phone: str, password: str = "OldPass123", role: str = "student") -> int:
    db = _TestSessionLocal()
    user = models.User(
        full_name="Test User",
        email=email,
        hashed_password=get_password_hash(password),
        dob=date(2000, 1, 1),
        is_minor=False,
        phone_number=phone,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    return user_id


def _login(email: str, password: str = "OldPass123") -> str:
    r = client.post("/v1/auth/login-json", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_admin_trigger_never_leaks_otp_or_token(monkeypatch):
    _make_user("admin-trigger@example.com", "+911111100001", role="admin")
    target_id = _make_user("target-trigger@example.com", "+911111100002")

    headers = {"Authorization": f"Bearer {_login('admin-trigger@example.com')}"}

    for expose_value in ("true", "false"):
        monkeypatch.setenv("CP_EXPOSE_AUTH_SECRETS", expose_value)

        r = client.post(
            f"/v1/admin/users/{target_id}/reset-password/trigger",
            headers=headers,
            json={"channel": "email"},
        )
        assert r.status_code == 200, r.text
        body = r.json()

        assert set(body.keys()) == {"success", "message"}
        assert body["success"] is True
        assert "otp" not in r.text.lower()
        assert "token" not in r.text.lower()


def test_admin_trigger_404_for_unknown_user(monkeypatch):
    _make_user("admin-trigger-404@example.com", "+911111100010", role="admin")
    headers = {"Authorization": f"Bearer {_login('admin-trigger-404@example.com')}"}

    r = client.post(
        "/v1/admin/users/999999/reset-password/trigger",
        headers=headers,
        json={"channel": "email"},
    )
    assert r.status_code == 404


def test_admin_direct_set_password_changes_password():
    _make_user("admin-direct@example.com", "+911111100003", role="admin")
    target_id = _make_user("target-direct@example.com", "+911111100004", password="OldPass123")

    headers = {"Authorization": f"Bearer {_login('admin-direct@example.com')}"}

    r = client.post(
        f"/v1/admin/users/{target_id}/reset-password/direct",
        headers=headers,
        json={"new_password": "BrandNewPass456"},
    )
    assert r.status_code == 200
    assert r.json() == {"success": True}

    old_login = client.post(
        "/v1/auth/login-json",
        json={"email": "target-direct@example.com", "password": "OldPass123"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/v1/auth/login-json",
        json={"email": "target-direct@example.com", "password": "BrandNewPass456"},
    )
    assert new_login.status_code == 200


def test_password_reset_logs_requires_admin():
    _make_user("student-logs@example.com", "+911111100005", role="student")
    headers = {"Authorization": f"Bearer {_login('student-logs@example.com')}"}

    r = client.get("/v1/admin/password-reset-logs", headers=headers)
    assert r.status_code == 403


def test_password_reset_logs_pagination_and_filtering():
    admin_id = _make_user("admin-logs@example.com", "+911111100006", role="admin")
    target_id = _make_user("target-logs@example.com", "+911111100007")

    headers = {"Authorization": f"Bearer {_login('admin-logs@example.com')}"}

    # One 'otp_sent' admin_reset row...
    trig = client.post(
        f"/v1/admin/users/{target_id}/reset-password/trigger",
        headers=headers,
        json={"channel": "email"},
    )
    assert trig.status_code == 200
    # ...and one 'completed' admin_reset row.
    direct = client.post(
        f"/v1/admin/users/{target_id}/reset-password/direct",
        headers=headers,
        json={"new_password": "AnotherPass789"},
    )
    assert direct.status_code == 200

    r = client.get(
        "/v1/admin/password-reset-logs",
        headers=headers,
        params={"user_id": target_id, "method": "admin_reset", "page": 1, "page_size": 25},
    )
    assert r.status_code == 200
    body = r.json()

    assert body["page"] == 1
    assert body["page_size"] == 25
    assert body["total"] == 2
    assert len(body["items"]) == 2

    for item in body["items"]:
        assert item["method"] == "admin_reset"
        assert item["user_id"] == target_id
        assert item["user_email"] == "target-logs@example.com"
        assert item["initiated_by_admin_id"] == admin_id
        assert item["initiated_by_admin_email"] == "admin-logs@example.com"
        # no secret material ever surfaces
        assert "otp" not in item
        assert "otp_hash" not in item

    assert {item["status"] for item in body["items"]} == {"otp_sent", "completed"}

    created_ats = [item["created_at"] for item in body["items"]]
    assert created_ats == sorted(created_ats, reverse=True)  # newest first

    # status filter narrows to just the completed row
    completed_only = client.get(
        "/v1/admin/password-reset-logs",
        headers=headers,
        params={"user_id": target_id, "status": "completed"},
    )
    assert completed_only.status_code == 200
    completed_body = completed_only.json()
    assert completed_body["total"] == 1
    assert completed_body["items"][0]["status"] == "completed"

    # page_size smaller than total exercises pagination
    paged = client.get(
        "/v1/admin/password-reset-logs",
        headers=headers,
        params={"user_id": target_id, "page": 1, "page_size": 1},
    )
    assert paged.status_code == 200
    paged_body = paged.json()
    assert paged_body["total"] == 2
    assert len(paged_body["items"]) == 1
