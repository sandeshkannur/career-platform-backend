# app/routers/admin_student_analytics.py
"""
Admin student drill-down analytics endpoint.
Powers the student detail panel inside the Funnel & Students tab.

GET /v1/admin-student-analytics/{student_id}
Auth: require_admin_or_counsellor
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app import models
from app.deps import get_db
from app.auth.auth import require_admin_or_counsellor
from app.services.counsellor_access import shadow_check_counsellor_access
from app.services.student_analytics_service import (
    get_student_row,
    build_student_analytics,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/{student_id}")
def get_student_analytics(
    student_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    # ------------------------------------------------------------------ #
    # Student info — 404 if not found
    # ------------------------------------------------------------------ #
    student_row = get_student_row(db, student_id)

    if not student_row:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found.")

    # Phase-1 counsellor assignment shadow check: log-only, never blocks.
    shadow_check_counsellor_access(
        db, current_user, student_id, "GET /v1/admin-student-analytics/{student_id}"
    )

    return build_student_analytics(db, student_id, student_row)


# ---------------------------------------------------------------------------
# Report downloads — per-student download log (report_downloads table)
# ---------------------------------------------------------------------------

@router.get("/{student_id}/report-downloads")
def get_student_report_downloads(
    student_id: int,
    limit: int = Query(50, ge=1, le=200, description="Max items to return (default 50, max 200)"),
    offset: int = Query(0, ge=0, description="Pagination offset (default 0)"),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    """
    GET /v1/admin-student-analytics/{student_id}/report-downloads

    Paginated list of a student's report download events (scorecard endpoint,
    pdf/json), newest first, plus a summary (total count + most recent).
    """
    # Student — 404 if not found (same pattern as the drill-down endpoint)
    student_row = db.execute(text("""
        SELECT s.id FROM students s WHERE s.id = :student_id
    """), {"student_id": student_id}).mappings().first()

    if not student_row:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found.")

    # Phase-1 counsellor assignment shadow check: log-only, never blocks.
    shadow_check_counsellor_access(
        db, current_user, student_id,
        "GET /v1/admin-student-analytics/{student_id}/report-downloads",
    )

    base = db.query(models.ReportDownload).filter(
        models.ReportDownload.student_id == student_id
    )

    total_downloads = base.count()

    rows = (
        base.outerjoin(
            models.Assessment,
            models.Assessment.id == models.ReportDownload.assessment_id,
        )
        .add_columns(models.Assessment.submitted_at.label("assessment_submitted_at"))
        .order_by(models.ReportDownload.downloaded_at.desc(), models.ReportDownload.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    downloads = [
        {
            "id":                      dl.id,
            "assessment_id":           dl.assessment_id,
            "assessment_submitted_at": assessment_submitted_at.isoformat() if assessment_submitted_at else None,
            "format":                  dl.format,
            "locale":                  dl.locale,
            "tier":                    dl.tier,
            # Attribution (nullable: rows predating the attribution columns)
            "downloaded_by_user_id":   dl.downloaded_by_user_id,
            "downloaded_by_role":      dl.downloaded_by_role,
            "downloaded_at":           dl.downloaded_at.isoformat() if dl.downloaded_at else None,
        }
        for dl, assessment_submitted_at in rows
    ]

    last_downloaded_at = downloads[0]["downloaded_at"] if offset == 0 and downloads else None
    if last_downloaded_at is None and total_downloads > 0:
        latest = base.order_by(models.ReportDownload.downloaded_at.desc()).first()
        last_downloaded_at = latest.downloaded_at.isoformat() if latest and latest.downloaded_at else None

    return {
        "student_id":         student_id,
        "summary": {
            "total_downloads":    total_downloads,
            "last_downloaded_at": last_downloaded_at,
        },
        "limit":    limit,
        "offset":   offset,
        "downloads": downloads,
    }
