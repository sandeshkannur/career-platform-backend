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

DATABASE_URL = os.getenv("DATABASE_URL", "")
SKIP_DB_WAIT = os.getenv("SKIP_DB_WAIT", "0")

print(f"DEBUG: POSTGRES_HOST from env: {os.getenv('POSTGRES_HOST')}")
print(f"DEBUG: POSTGRES_PORT from env: {os.getenv('POSTGRES_PORT')}")
print(f"DEBUG: POSTGRES_USER from env: {os.getenv('POSTGRES_USER')}")
print(f"DEBUG: POSTGRES_DB from env: {os.getenv('POSTGRES_DB')}")
print(f"DEBUG: DATABASE_URL from env: {DATABASE_URL}")
print(f"DEBUG: SKIP_DB_WAIT from env: {SKIP_DB_WAIT}")

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from app.core.openapi import apply_openapi_security
from app.core.startup import run_startup_tasks
import app.models  # noqa: F401


# ============================================================
# 3) APPLICATION FACTORY (PR-CLEAN-04 STEP 2)
# ============================================================

def create_app() -> FastAPI:
    """
    PR-CLEAN-04 Step 2: App Factory Pattern (create_app)

    Goals:
    - Reduce global side effects over time (future steps).
    - Improve testability and production safety.
    - Keep behavior IDENTICAL in this step.

    IMPORTANT:
    - No route path changes
    - No DB schema changes
    - No env changes
    - No middleware changes
    - Only structural refactor
    """
    # ------------------------------------------------------------
    # STARTUP ORCHESTRATION (PR-CLEAN-04 Step 4)
    # ------------------------------------------------------------
    run_startup_tasks(DATABASE_URL, SKIP_DB_WAIT)

    # ------------------------------------------------------------
    # 3A) FASTAPI APP CREATION + CORS (CONFIGURE ONCE)
    # ------------------------------------------------------------
    app = FastAPI(title="Career Counseling API")

    # ✅ CORS (DEV)
    # Frontend uses credentials: "include" (cookie-ready refresh token architecture),
    # so allow_origins MUST be explicit (not "*") when allow_credentials=True.
    app.add_middleware(
        CORSMiddleware,
            allow_origins=[
                "http://localhost:5173",       # Vite dev server
                "http://127.0.0.1:5173",       # sometimes used by browsers/tools
                "https://mapyourcareer.in",    # production frontend
                "https://www.mapyourcareer.in" # production frontend (www)
            ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health_check():
        return {"status": "ok"}
    # ------------------------------------------------------------
    # 3B) OPENAPI CUSTOMIZATION (JWT BEARER SUPPORT IN SWAGGER)
    # ------------------------------------------------------------
    apply_openapi_security(app)

    # ------------------------------------------------------------
    # 3C) DB TABLE CREATION (DEV MODE / NO MIGRATIONS YET)
    # ------------------------------------------------------------
    # PR-CLEAN-04 Step 4:
    # DB wait + create_all is now handled by run_startup_tasks()
    # (kept out of create_app() to avoid duplicate execution).
    # ------------------------------------------------------------
    # 3D) BASIC HEALTH ENDPOINT
    # ------------------------------------------------------------
    @app.get("/", tags=["Health"])
    def root():
        return {"message": "Career Counseling API is up and running."}

    # ------------------------------------------------------------
    # 3E) ROUTERS (ALL API ROUTES MOUNTED UNDER /v1)
    # ------------------------------------------------------------

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
    api_v1.include_router(careers.router, prefix="", tags=["Careers"])
    api_v1.include_router(skills.router, prefix="", tags=["Skills"])
    api_v1.include_router(key_skills_router, prefix="/key-skills", tags=["Key Skills"])

    # Student-related
    api_v1.include_router(students.router, prefix="", tags=["Students"])
    api_v1.include_router(student_skill_map.router, prefix="", tags=["Student ↔ Skill Map"])
    api_v1.include_router(student_keyskill_map.router, prefix="", tags=["StudentKeySkillMap"])

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

    # ------------------------------------------------------------
    # 3F) STARTUP DEBUG (OPTIONAL)
    # ------------------------------------------------------------
    print("INFO: Application startup sequence complete in main.py.")
    print("INFO: Registered FastAPI Routes:")
    for route in app.routes:
        print(f" - {route.path}")

    return app


# ============================================================
# 4) GLOBAL APP INSTANCE (Uvicorn entrypoint requires app.main:app)
# ============================================================

app = create_app()
