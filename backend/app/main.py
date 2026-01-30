# app/main.py
"""
Career Counseling API - main entrypoint

Key notes (DEV):
- CORS is configured ONCE (do not duplicate CORSMiddleware).
- Because the frontend uses fetch(..., credentials: "include") for refresh-token readiness,
  allow_origins MUST be explicit (cannot be "*") when allow_credentials=True.
"""

import os
from dotenv import load_dotenv

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.database import engine, Base
from app.wait_for_db import wait_for_postgres
import app.models  # noqa: F401  # ensures SQLAlchemy models are registered


# ============================================================
# 1) ENVIRONMENT LOADING / STARTUP FLAGS
# ============================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(BASE_DIR, ".env")

print(f"INFO: Attempting to load .env file from: {dotenv_path}")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    print(f"INFO: Successfully loaded .env file from: {dotenv_path}")
else:
    print(
        f"WARNING: .env file not found at: {dotenv_path}. "
        "Using system environment variables or defaults."
    )

# Read key env vars used by startup logic
DATABASE_URL = os.getenv("DATABASE_URL", "")
SKIP_DB_WAIT = os.getenv("SKIP_DB_WAIT", "0")

# Optional debug prints (safe)
print(f"DEBUG: POSTGRES_HOST from env: {os.getenv('POSTGRES_HOST')}")
print(f"DEBUG: POSTGRES_PORT from env: {os.getenv('POSTGRES_PORT')}")
print(f"DEBUG: POSTGRES_USER from env: {os.getenv('POSTGRES_USER')}")
print(f"DEBUG: POSTGRES_DB from env: {os.getenv('POSTGRES_DB')}")
print(f"DEBUG: DATABASE_URL from env: {DATABASE_URL}")
print(f"DEBUG: SKIP_DB_WAIT from env: {SKIP_DB_WAIT}")


# ============================================================
# 2) WAIT FOR DATABASE (POSTGRES) IF REQUIRED
# ============================================================

# Wait only when:
# - NOT using sqlite
# - SKIP_DB_WAIT is not enabled
if not DATABASE_URL.startswith("sqlite") and SKIP_DB_WAIT != "1":
    wait_for_postgres(
        host=os.getenv("POSTGRES_HOST", "db"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "counseling"),
        password=os.getenv("POSTGRES_PASSWORD", "password"),
        db=os.getenv("POSTGRES_DB", "counseling_db"),
    )
else:
    print("INFO: Skipping wait_for_postgres (using SQLite or SKIP_DB_WAIT=1)")


# ============================================================
# 3) FASTAPI APP CREATION + CORS (CONFIGURE ONCE)
# ============================================================

app = FastAPI(title="Career Counseling API")

# ✅ CORS (DEV)
# Frontend uses credentials: "include" (cookie-ready refresh token architecture),
# so allow_origins MUST be explicit (not "*") when allow_credentials=True.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",      # Vite dev server
        "http://127.0.0.1:5173",      # sometimes used by browsers/tools
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 4) OPENAPI CUSTOMIZATION (JWT BEARER SUPPORT IN SWAGGER)
# ============================================================

def custom_openapi():
    """
    Adds a Bearer/JWT scheme so Swagger's 'Authorize' button works.
    This aligns with OAuth2PasswordBearer token usage in dependencies.
    """
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title="Career Counseling API",
        version="0.1.0",
        description="Career Counseling API with JWT Bearer authentication",
        routes=app.routes,
    )

    schema.setdefault("components", {}).setdefault("securitySchemes", {})
    schema["components"]["securitySchemes"]["OAuth2PasswordBearer"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }

    # Apply default security globally unless an operation overrides it
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if "security" not in operation:
                operation["security"] = [{"OAuth2PasswordBearer": []}]

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


# ============================================================
# 5) DB TABLE CREATION (DEV MODE / NO MIGRATIONS YET)
# ============================================================

# Your current behavior: if SKIP_DB_WAIT=1 we skip create_all too.
if SKIP_DB_WAIT != "1":
    Base.metadata.create_all(bind=engine)


# ============================================================
# 6) BASIC HEALTH ENDPOINT
# ============================================================

@app.get("/", tags=["Health"])
def root():
    return {"message": "Career Counseling API is up and running."}


# ============================================================
# 7) ROUTERS (ALL API ROUTES MOUNTED UNDER /v1)
# ============================================================

# --- Import routers (kept together for clarity) ---
from app.auth.auth import router as auth_router
from app.routers import (
    career_clusters,
    careers,
    skills,
    students,
    student_skill_map,
    student_keyskill_map,
    career_keyskill_map,
    recommendations,
    analytics,         # generic analytics / placeholder
    paid_analytics,    # paid analytics per student
    admin,
    assessments,
    scorecard,
    content,
)

from app.routers.key_skills import router as key_skills_router

# ✅ B5 router (student questions random)
from app.routers.questions_random import router as questions_random_router

# ✅ B6 router (student localized questions list)
from app.routers.questions import router as questions_router

# ✅ B10 Student dashboard (B10) - avoid double prefix by mounting here
from app.routers.student_dashboard import router as student_dashboard_router

# B11: Student assessment history (read-only, student-facing)
from app.routers import student_assessment_history

# B12: Student results history (read-only, student-facing)
from app.routers.student_results_history import router as student_results_history_router

# B13: Consent verification (compliance, guardian-facing)
from app.routers.consent import router as consent_router

# B14: Student report download payload (read-only)
from app.routers.reports import router as reports_router

# --- Create a single /v1 aggregator router ---
api_v1 = APIRouter(prefix="/v1")

# Auth + Admin + Assessments
api_v1.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_v1.include_router(admin.router, prefix="/admin", tags=["Admin Panel"])
api_v1.include_router(assessments.router, prefix="/assessments", tags=["Assessments"])

# Core reference data
api_v1.include_router(career_clusters.router, prefix="/career-clusters", tags=["Career Clusters"])
api_v1.include_router(careers.router, prefix="/careers", tags=["Careers"])
api_v1.include_router(skills.router, prefix="/skills", tags=["Skills"])
api_v1.include_router(key_skills_router, prefix="/key-skills", tags=["Key Skills"])

# Student-related
api_v1.include_router(students.router, prefix="/students", tags=["Students"])
api_v1.include_router(student_skill_map.router, prefix="/student-skill-map", tags=["Student ↔ Skill Map"])
api_v1.include_router(student_keyskill_map.router, prefix="/student-keyskill-map", tags=["Student ↔ KeySkill Map"])

# Mappings + recommendations
api_v1.include_router(career_keyskill_map.router, prefix="/career-keyskill-map", tags=["Career ↔ KeySkill Map"])
api_v1.include_router(recommendations.router, prefix="/recommendations", tags=["Recommendations"])

# Analytics
api_v1.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_v1.include_router(paid_analytics.router, prefix="", tags=["Paid Analytics"])
api_v1.include_router(scorecard.router, prefix="", tags=["Scorecard"])

# ✅ B5: student random question delivery
api_v1.include_router(questions_random_router, prefix="", tags=["Questions"])

# ✅ B6: student localized question list
api_v1.include_router(questions_router, prefix="", tags=["Questions"])

# Student dashboard (B10) - avoid double prefix by mounting here
api_v1.include_router(student_dashboard_router, prefix="/students", tags=["Students"])

# B11: Expose assessment history for students (ownership enforced)
api_v1.include_router(student_assessment_history.router, prefix="", tags=["Students"])

# B12: Expose historical career results for students (ownership enforced, read-only)
api_v1.include_router(student_results_history_router, prefix="", tags=["Students"])

# B13: Consent verification (compliance, guardian-facing)
api_v1.include_router(consent_router, prefix="", tags=["Consent"])

# B14: Student report endpoint (read-only, ownership enforced)
api_v1.include_router(reports_router, prefix="", tags=["Reports"])

api_v1.include_router(content.router, prefix="/content", tags=["Content"])

# --- Mount /v1 on app ---
app.include_router(api_v1)


# ============================================================
# 8) STARTUP DEBUG (OPTIONAL)
# ============================================================

print("INFO: Application startup sequence complete in main.py.")
print("INFO: Registered FastAPI Routes:")
for route in app.routes:
    print(f" - {route.path}")
