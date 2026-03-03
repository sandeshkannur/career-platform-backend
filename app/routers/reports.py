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
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.auth import get_current_active_user
from app.deps import get_db
from app.services import report_builder
from app.projections.student_safe import project_student_safe

router = APIRouter(prefix="/reports", tags=["Reports"])

# Keep explicit to avoid accidental version drift.
SUPPORTED_VERSIONS = {"v1"}

@router.get("/scorecard/{student_id}")
def get_scorecard_report(
    student_id: int,
    view: str = Query(default="student", description="student|counsellor|admin (role-enforced)"),
    format: str = Query(default="json", description="json|html|pdf (pdf deferred)"),
    locale: str = Query(default="en", description="Locale like en, kn-IN"),
    assessment_id: int | None = Query(default=None, description="Optional deterministic assessment snapshot"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    PR18 — Canonical report endpoint (mobile + desktop compatible)
    - Deterministic snapshot: assessment_id optional, else latest
    - Projection-based views: student/counsellor/admin (server enforced)
    - Formats: json + html now, pdf deferred (501)
    """

    # ---------------------------------------------------------
    # 1) Enforce RBAC + view projection
    # ---------------------------------------------------------
    role = getattr(current_user, "role", None)

    # Force student-safe mode always for students
    if role == "student":
        enforced_view = "student"
    elif role == "counsellor":
        enforced_view = "counsellor" if view not in ("student", "counsellor") else view
    elif role == "admin":
        enforced_view = view if view in ("student", "counsellor", "admin") else "admin"
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid role")

    # Validate requested format
    if format not in ("json", "html", "pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {format}",
        )

    # PDF is deferred in beta (deterministic behavior)
    if format == "pdf":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="PDF export is not available in beta. Use format=html.",
        )

    # ---------------------------------------------------------
    # 2) Ownership enforcement (student can only see their own report)
    # ---------------------------------------------------------
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    if role == "student" and student.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this student's report",
        )

    # ---------------------------------------------------------
    # 3) Resolve deterministic source assessment + results
    # ---------------------------------------------------------
    try:
        student_obj, assessment, assessment_result = report_builder.resolve_report_source(
            db,
            student_id=student_id,
            assessment_id=assessment_id,
        )
    except report_builder.ReportSourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except report_builder.ReportNotReadyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not ready")

    # ---------------------------------------------------------
    # 4) Build canonical ReportDocument (student-safe guard inside builder)
    # ---------------------------------------------------------
    locale = report_builder.normalize_locale(locale)
    
    doc = report_builder.build_report_document(
        db,
        student=student_obj,
        assessment=assessment,
        assessment_result=assessment_result,
        view=enforced_view,
        locale=locale,
    )

    # ---------------------------------------------------------
    # 5) Format response
    # ---------------------------------------------------------
    if format == "html":
        html = report_builder.render_report_html(doc)
        return HTMLResponse(content=html, status_code=200)

    # format == "json"
    return schemas.ReportResponse(
        student_id=student_id,
        scoring_config_version=assessment.scoring_config_version,  # keep existing field meaning: config version
        report_ready=True,
        report_format="json",
        generated_at=datetime.now(timezone.utc),
        pdf_download_url=None,
        message="Report generated",
        report_payload=project_student_safe(doc.model_dump()) if enforced_view == "student" else doc.model_dump(),
    )

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
    payload_json: Dict[str, Any] = project_student_safe(analytics_row.payload_json or {})

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
