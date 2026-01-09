# app/routers/reports.py
"""
B14 — Student Report Endpoint (JSON / PDF Placeholder)

Route:
  GET /v1/reports/{student_id}?version=v1

Behavior:
- JWT protected (student-facing)
- Ownership enforced (students.user_id == current_user.id)
- Read-only: pulls latest analytics snapshot from student_analytics_summary
- Deterministic: if multiple rows exist, newest computed_at wins
- Version-aware: default v1, rejects unsupported versions
"""

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.auth import get_current_active_user
from app.deps import get_db

router = APIRouter(prefix="/reports", tags=["Reports"])

# Keep explicit to avoid accidental version drift.
SUPPORTED_VERSIONS = {"v1"}


@router.get("/{student_id}", response_model=schemas.ReportResponse)
def get_student_report(
    student_id: int,
    version: str = Query(default="v1", description="Report version (default: v1)"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> schemas.ReportResponse:
    # ---------------------------------------------------------
    # 1) Validate version (400 if unsupported)
    # ---------------------------------------------------------
    if version not in SUPPORTED_VERSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported version: {version}",
        )

    # ---------------------------------------------------------
    # 2) Confirm student exists (404) + enforce ownership (403)
    # ---------------------------------------------------------
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    if student.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this student's report",
        )

    # ---------------------------------------------------------
    # 3) Fetch latest analytics snapshot for (student_id, version)
    #    Deterministic selection: computed_at DESC
    # ---------------------------------------------------------
    analytics_row = (
        db.query(models.StudentAnalyticsSummary)
        .filter(
            models.StudentAnalyticsSummary.student_id == student_id,
            models.StudentAnalyticsSummary.scoring_config_version == version,
        )
        .order_by(models.StudentAnalyticsSummary.computed_at.desc())
        .first()
    )

    # ---------------------------------------------------------
    # 4) If analytics missing => report not ready (404)
    # ---------------------------------------------------------
    if not analytics_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not ready",
        )

    # ---------------------------------------------------------
    # 5) Build response payload (JSON + PDF placeholders)
    # ---------------------------------------------------------
    payload_json: Dict[str, Any] = analytics_row.payload_json or {}

    report_payload: Dict[str, Any] = {
        "analytics": payload_json,
        "report_meta": {
            "source_table": models.StudentAnalyticsSummary.__tablename__,
            "computed_at": analytics_row.computed_at,
        },
    }

    return schemas.ReportResponse(
        student_id=student_id,
        scoring_config_version=version,
        report_ready=True,
        report_format="pdf_placeholder",  # explicit placeholder for now
        generated_at=datetime.now(timezone.utc),
        pdf_download_url=None,
        message="PDF generation not enabled yet",
        report_payload=report_payload,
    )
