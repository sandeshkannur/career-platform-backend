# backend/tests/conftest.py

import os
import pytest
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, text

# -----------------------------------------------------------------------------
# 1) Choose DB for tests
# -----------------------------------------------------------------------------
# - If TEST_DATABASE_URL is set (Docker/Postgres), use that (recommended)
# - Otherwise fall back to SQLite (note: JSONB models won't work on SQLite)
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

if TEST_DATABASE_URL:
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
else:
    SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test.db"
    engine = create_engine(
        SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False}
    )

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# -----------------------------------------------------------------------------
# 1.a) Override the app's SessionLocal so ALL app DB sessions use the test DB
# -----------------------------------------------------------------------------
# This ensures that when the FastAPI app creates DB sessions, it uses the same
# TestingSessionLocal (Postgres via TEST_DATABASE_URL or SQLite fallback).
import app.database as _database
_database.SessionLocal = TestingSessionLocal

# -----------------------------------------------------------------------------
# 2) Import the real FastAPI app and SQLAlchemy Base
# -----------------------------------------------------------------------------
from app.main import app
from app.database import Base
from app.deps import get_db
from app.models import User
from app.auth.auth import get_password_hash
from sqlalchemy import text

# -----------------------------------------------------------------------------
# 3) Override FastAPI's get_db dependency to use the test DB session
# -----------------------------------------------------------------------------
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

def _reset_db(db):
    dialect = db.get_bind().dialect.name  # "postgresql" or "sqlite"

    if dialect == "postgresql":
        db.execute(text("TRUNCATE TABLE assessments, assessment_results, users RESTART IDENTITY CASCADE;"))
    else:
        # SQLite: TRUNCATE not supported; use DELETE
        # Order matters if FK constraints are enforced.
        db.execute(text("DELETE FROM assessment_results;"))
        db.execute(text("DELETE FROM assessments;"))
        db.execute(text("DELETE FROM users;"))

        # Optional: reset autoincrement counters in SQLite
        # (only works if sqlite_sequence exists)
        try:
            db.execute(text("DELETE FROM sqlite_sequence WHERE name IN ('assessments','assessment_results','users');"))
        except Exception:
            pass

    db.commit()

# -----------------------------------------------------------------------------
# 4) Create/drop tables once per test session
# -----------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def prepare_database():
    # Clean slate (useful when re-running tests against Postgres)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

# -----------------------------------------------------------------------------
# 5) Provide a TestClient for API tests
# -----------------------------------------------------------------------------
@pytest.fixture
def client():
    return TestClient(app)

# -----------------------------------------------------------------------------
# 6) Seed an admin user and return its JWT token
# -----------------------------------------------------------------------------
@pytest.fixture
def admin_token(client):
    db = TestingSessionLocal()

    # Wipe out any existing users so we never hit UNIQUE collisions
    _reset_db(db)

    admin = User(
        full_name="Admin User",
        email="admin@example.com",
        hashed_password=get_password_hash("strongpass123"),
        dob=date(1980, 1, 1),
        is_minor=False,
    )
    setattr(admin, "role", "admin")
    db.add(admin)
    db.commit()
    db.close()

    resp = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "strongpass123"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    return resp.json()["access_token"]

# -----------------------------------------------------------------------------
# 7) Seed a student user and return its JWT token
# -----------------------------------------------------------------------------
@pytest.fixture
def student_token(client):
    # Clear out users so test starts clean
    db = TestingSessionLocal()
    _reset_db(db)
    db.close()

    # Sign up a new student via the API
    signup_resp = client.post(
        "/v1/auth/signup",
        json={
            "full_name": "Test Student",
            "email": "student@example.com",
            "password": "studentpass123",
            "dob": "2006-01-01",
        },
    )
    assert signup_resp.status_code == 201, (
        f"Signup failed: {signup_resp.status_code} {signup_resp.text}"
    )

    # Log in to get token
    login_resp = client.post(
        "/v1/auth/login",
        json={"email": "student@example.com", "password": "studentpass123"},
    )
    assert login_resp.status_code == 200, (
        f"Login failed: {login_resp.status_code} {login_resp.text}"
    )
    return login_resp.json()["access_token"]
