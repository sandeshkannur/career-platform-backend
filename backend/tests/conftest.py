# backend/tests/conftest.py

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import date

# 1) point at a disposable SQLite DB
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 1.a) override the app's SessionLocal so ALL sessions use SQLite
import app.database as _database
_database.SessionLocal = TestingSessionLocal

# 2) bring in your real app and Base
from app.main import app
from app.database import Base
from app.deps import get_db
from app.models import User
from app.auth.auth import get_password_hash

# 3) override the FastAPI get_db dependency
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# 4) create/drop tables once per test session
@pytest.fixture(scope="session", autouse=True)
def prepare_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

# 5) provide a TestClient for tests
@pytest.fixture
def client():
    return TestClient(app)

# 6) seed an admin user and return its JWT
@pytest.fixture
def admin_token(client):
    db = TestingSessionLocal()

    # wipe out any existing users so we never hit UNIQUE collisions
    db.query(User).delete()
    db.commit()

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

# 7) seed a student user and return its JWT
@pytest.fixture
def student_token(client):
    # clear out users so test starts clean
    db = TestingSessionLocal()
    db.query(User).delete()
    db.commit()
    db.close()

    # sign up a new student via the API
    signup_resp = client.post(
        "/v1/auth/signup",
        json={
            "full_name": "Test Student",
            "email": "student@example.com",
            "password": "studentpass123",
            "dob": "2006-01-01"
        },
    )
    assert signup_resp.status_code == 201, f"Signup failed: {signup_resp.status_code} {signup_resp.text}"

    # log in to get token
    login_resp = client.post(
        "/v1/auth/login",
        json={"email": "student@example.com", "password": "studentpass123"},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.status_code} {login_resp.text}"
    return login_resp.json()["access_token"]
