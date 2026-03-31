"""
Admin router package.
Combines all admin sub-routers into a single router that main.py mounts
under /v1/admin. main.py requires zero changes — it still imports:
    from app.routers import admin
    api_v1.include_router(admin.router, prefix="/admin", tags=["Admin Panel"])

Sub-modules:
  ingest.py     — 14 bulk data upload endpoints
  questions.py  — 2 question creation endpoints
  users.py      — 5 user and skill-map management endpoints
  validation.py — 4 knowledge-pack and explainability validation endpoints
"""
from fastapi import APIRouter, Depends
from app.auth.auth import require_role

from app.routers.admin import ingest, questions, users, validation

# Top-level router — all sub-routers inherit the admin role gate
router = APIRouter(
    tags=["Admin Panel"],
    dependencies=[Depends(require_role("admin"))],
)

router.include_router(ingest.router)
router.include_router(questions.router)
router.include_router(users.router)
router.include_router(validation.router)
