# app/routers/student_dashboard.py

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from app.routers.scorecard import reverse_tier
from app import models, schemas
from app.auth.auth import get_current_active_user
from app.deps import get_db
from app.projections.student_safe import project_student_safe


router = APIRouter(
    tags=["Students"],
    # NOTE: Intentionally no prefix here.
    # We mount this router under /v1 with prefix="/students" in main.py so we get:
    #   /v1/students/{student_id}/dashboard
    # without impacting the existing double-prefix Students CRUD endpoints:
    #   /v1/students/students/...
)


@router.get(
    "/{student_id}/dashboard",
    response_model=schemas.StudentDashboardResponse,
)
def get_student_dashboard(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    B10: GET /v1/students/{student_id}/dashboard
    Type: Aggregation (real-time, read-only)

    Auth:
    - JWT required (current_user resolved via dependency)

    Authorization:
    - Student can ONLY access their own dashboard
      (students.user_id must match current_user.id)

    Reads:
    - students
    - assessments (note: assessments are linked to users via assessments.user_id)
    - student_analytics_summary (B9 snapshot)
    - student_skill_scores (optional top skills)

    Writes: none
    """

    scoring_config_version = "v1"

    # ------------------------------------------------------------
    # 1) Validate student exists + strict ownership check
    # ------------------------------------------------------------
    student = (
        db.query(models.Student)
        .filter(models.Student.id == student_id)
        .first()
    )
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    # Ownership: students.user_id -> users.id
    if student.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this student's dashboard",
        )

    # ------------------------------------------------------------
    # 2) Assessment KPIs (count + last submitted date)
    # ------------------------------------------------------------
    # IMPORTANT:
    # Your assessments table links to users (assessments.user_id), not students.
    total_assessments = (
        db.query(func.count(models.Assessment.id))
        .filter(models.Assessment.user_id == current_user.id)
        .scalar()
    ) or 0

    # Latest assessment by submitted_at (exists in DB schema)
    last_assessment = (
        db.query(models.Assessment)
        .filter(models.Assessment.user_id == current_user.id)
        .order_by(desc(models.Assessment.submitted_at))
        .first()
    )

    last_submitted_at: Optional[datetime] = None
    if last_assessment is not None:
        last_submitted_at = last_assessment.submitted_at

    assessment_kpis = schemas.StudentDashboardAssessmentKPIs(
        total_assessments=total_assessments,
        last_submitted_at=last_submitted_at,
    )

    # No assessments yet -> deterministic empty response
    if total_assessments == 0:
        return schemas.StudentDashboardResponse(
            student_id=student_id,
            scoring_config_version=scoring_config_version,
            assessment_kpis=assessment_kpis,
            keyskill_analytics=None,
            top_skills=[],
            message="Take your first assessment to see your dashboard insights.",
        )

    # ------------------------------------------------------------
    # 3) Pull analytics snapshot from B9 (preferred)
    #    Gracefully continue if the additive B9 table is not present
    # ------------------------------------------------------------
    analytics_row = None
    keyskill_analytics: Optional[schemas.StudentDashboardKeyskillAnalytics] = None

    try:
        analytics_row = (
            db.query(models.StudentAnalyticsSummary)
            .filter(models.StudentAnalyticsSummary.student_id == student_id)
            .filter(models.StudentAnalyticsSummary.scoring_config_version == scoring_config_version)
            .first()
        )
    except ProgrammingError:
        db.rollback()
        analytics_row = None

    if analytics_row and getattr(analytics_row, "payload_json", None):
        payload = project_student_safe(analytics_row.payload_json)

        # Safe extraction with defaults (deterministic)
        if isinstance(payload, dict):
            keyskill_analytics = schemas.StudentDashboardKeyskillAnalytics(
                overall_keyskill_summary=payload.get("overall_keyskill_summary", {}) or {},
                distribution=payload.get("distribution", {}) or {},
                top_keyskills=payload.get("top_keyskills", []) or [],
            )

    # ------------------------------------------------------------
    # 4) Optional: top skills from latest assessment (B7) (deterministic)
    # ------------------------------------------------------------
    top_skills: List[schemas.StudentDashboardTopSkill] = []

    if last_assessment is not None:
        try:
            scores = (
                db.query(
                    models.StudentSkillScore.skill_id,
                    models.StudentSkillScore.assessment_id,
                    models.StudentSkillScore.scaled_0_100,
                )
                .filter(models.StudentSkillScore.assessment_id == last_assessment.id)
                .filter(models.StudentSkillScore.scoring_config_version == scoring_config_version)
                .order_by(desc(models.StudentSkillScore.scaled_0_100), models.StudentSkillScore.skill_id)
                .limit(10)
                .all()
            )

            top_skills = [
                schemas.StudentDashboardTopSkill(
                    skill_id=s.skill_id,
                    scaled_0_100=s.scaled_0_100,
                    tier=reverse_tier(s.scaled_0_100) if s.scaled_0_100 is not None else None,
                    assessment_id=s.assessment_id,
                )
                for s in scores
            ]
        except ProgrammingError:
            db.rollback()
            top_skills = []

    # Deterministic message for UX if snapshot not available yet
    msg: Optional[str] = None
    if keyskill_analytics is None:
        msg = "Your dashboard insights are being prepared. Some analytics may not be available yet."

    return schemas.StudentDashboardResponse(
        student_id=student_id,
        scoring_config_version=scoring_config_version,
        assessment_kpis=assessment_kpis,
        keyskill_analytics=keyskill_analytics,
        top_skills=top_skills,
        message=msg,
    )
