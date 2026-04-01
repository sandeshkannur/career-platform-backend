# app/main.py
"""
Career Counseling API — application entrypoint.

Structure:
  - Environment loading (.env → system env fallback)
  - create_app() factory: CORS, health endpoints, router wiring
  - Global app instance for Uvicorn: app.main:app

CORS note: allow_origins must be explicit (not "*") because the frontend
uses credentials: "include" for cookie-ready refresh token architecture.
"""
import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ============================================================
# ENVIRONMENT LOADING
# Load .env file if present; fall back to system environment variables.
# In production (Docker/EC2) environment variables are injected directly
# and .env will not be present — that is expected and safe.
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(BASE_DIR, ".env")

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    logger.info("Loaded .env file from: %s", dotenv_path)
else:
    logger.info("No .env file found at %s — using system environment variables.", dotenv_path)

DATABASE_URL = os.getenv("DATABASE_URL", "")
SKIP_DB_WAIT = os.getenv("SKIP_DB_WAIT", "0")

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from app.core.openapi import apply_openapi_security
from app.core.startup import run_startup_tasks
import app.models  # noqa: F401 — ensures all ORM models are registered before create_all()


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

    # ADM-B02: SME public form endpoints (token-only auth, no login required)
    from app.routers.admin.submissions import public_router as sme_public_router

    # --- Create a single /v1 aggregator router ---
    api_v1 = APIRouter(prefix="/v1")

    # Auth + Admin + Assessments
    api_v1.include_router(auth_router, prefix="/auth", tags=["Authentication"])
    api_v1.include_router(admin.router, prefix="/admin", tags=["Admin Panel"])
    api_v1.include_router(sme_public_router, prefix="", tags=["SME Form"])                        # → /v1/sme/form/*
    api_v1.include_router(assessments.router, prefix="/assessments", tags=["Assessments"])

    # Core reference data
    api_v1.include_router(career_clusters.router, prefix="/career-clusters", tags=["Career Clusters"])
    api_v1.include_router(careers.router, prefix="", tags=["Careers"])                          # → /v1/careers/*
    api_v1.include_router(skills.router, prefix="", tags=["Skills"])                            # → /v1/skills/*
    api_v1.include_router(key_skills_router, prefix="/key-skills", tags=["Key Skills"])

    # Student-related
    api_v1.include_router(students.router, prefix="", tags=["Students"])                        # → /v1/students/*
    api_v1.include_router(student_skill_map.router, prefix="", tags=["Student ↔ Skill Map"])    # → /v1/students/*/skill-map
    api_v1.include_router(student_keyskill_map.router, prefix="", tags=["StudentKeySkillMap"])  # → /v1/students/*/keyskill-map

    # Mappings + recommendations
    api_v1.include_router(career_keyskill_map.router, prefix="/career-keyskill-map", tags=["Career ↔ KeySkill Map"])
    api_v1.include_router(recommendations.router, prefix="/recommendations", tags=["Recommendations"])

    # Analytics
    api_v1.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
    api_v1.include_router(paid_analytics.router, prefix="", tags=["Paid Analytics"])            # → /v1/paid-analytics/*
    api_v1.include_router(scorecard.router, prefix="", tags=["Scorecard"])                      # → /v1/analytics/scorecard/*

    # ✅ B5: student random question delivery
    api_v1.include_router(questions_random_router, prefix="", tags=["Questions"])               # → /v1/questions/random

    # ✅ B6: student localized question list
    api_v1.include_router(questions_router, prefix="", tags=["Questions"])                      # → /v1/questions/*

    # Student dashboard (B10) - avoid double prefix by mounting here
    api_v1.include_router(student_dashboard_router, prefix="/students", tags=["Students"])

    # B11: Expose assessment history for students (ownership enforced)
    api_v1.include_router(student_assessment_history.router, prefix="", tags=["Students"])      # → /v1/students/*/assessments

    # B12: Expose historical career results for students (ownership enforced, read-only)
    api_v1.include_router(student_results_history_router, prefix="", tags=["Students"])         # → /v1/students/*/results

    # B13: Consent verification (compliance, guardian-facing)
    api_v1.include_router(consent_router, prefix="", tags=["Consent"])                          # → /v1/consent/*

    # B14: Student report endpoint (read-only, ownership enforced)
    api_v1.include_router(reports_router, prefix="", tags=["Reports"])                          # → /v1/reports/*

    api_v1.include_router(content.router, prefix="/content", tags=["Content"])

    # --- Mount /v1 on app ---
    app.include_router(api_v1)

    # ------------------------------------------------------------
    # 3F) STARTUP COMPLETE
    # Route list is available at /openapi.json — no need to print here.
    # ------------------------------------------------------------
    logger.info("Application startup complete. %d routes registered.", len(app.routes))

    return app


# ============================================================
# 4) GLOBAL APP INSTANCE (Uvicorn entrypoint requires app.main:app)
# ============================================================

app = create_app()
