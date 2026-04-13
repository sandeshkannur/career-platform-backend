"""
Scoring engine health dashboard.

  GET /v1/admin/engine/health

Read-only. Admin auth required. No writes, no scoring logic changes.
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.deps import get_db
from app.auth.auth import require_role, get_current_active_user

router = APIRouter(
    tags=["Admin Panel"],
    dependencies=[Depends(require_role("admin"))],
)

SCORING_CONFIG_VERSION = "v1"


def _int(val) -> int:
    """Safely coerce to int."""
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


def _float_or_none(val):
    """Safely coerce to float, return None on failure."""
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


@router.get(
    "/engine/health",
    summary="Scoring engine health dashboard (admin)",
)
def engine_health(
    db: Session = Depends(get_db),
    _=Depends(get_current_active_user),
):
    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start  = today_start - timedelta(days=today_start.weekday())  # Monday
    day14_start = today_start - timedelta(days=13)                      # 14-day window

    # ------------------------------------------------------------------
    # 1. Assessment counts — today / this week / total
    # ------------------------------------------------------------------
    counts_row = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE submitted_at >= :today)               AS today,
            COUNT(*) FILTER (WHERE submitted_at >= :week_start)          AS this_week,
            COUNT(*)                                                      AS total,
            MAX(submitted_at)                                             AS last_at
        FROM assessments
    """), {"today": today_start, "week_start": week_start}).mappings().one()

    assessments_today    = _int(counts_row["today"])
    assessments_this_week = _int(counts_row["this_week"])
    assessments_total    = _int(counts_row["total"])
    last_assessment_at   = counts_row["last_at"]
    if last_assessment_at is not None and hasattr(last_assessment_at, "isoformat"):
        last_assessment_at = last_assessment_at.isoformat()

    # ------------------------------------------------------------------
    # 2. Results generated today
    # ------------------------------------------------------------------
    results_today_row = db.execute(text("""
        SELECT COUNT(*) AS cnt
        FROM assessment_results
        WHERE generated_at >= :today
    """), {"today": today_start}).mappings().one()
    results_generated_today = _int(results_today_row["cnt"])

    # ------------------------------------------------------------------
    # 3. Avg completion time (seconds)
    #    Assessment has no created_at — proxy: use the earliest response
    #    submitted_at for each assessment via assessment_responses.
    #    Falls back to null if responses table is not available.
    # ------------------------------------------------------------------
    avg_completion_time_seconds = None
    try:
        avg_row = db.execute(text("""
            SELECT AVG(
                EXTRACT(EPOCH FROM (
                    a.submitted_at - MIN(ar.created_at)
                ))
            ) AS avg_secs
            FROM assessments a
            JOIN assessment_responses ar ON ar.assessment_id = a.id
            GROUP BY a.id, a.submitted_at
        """)).mappings().all()
        # avg_row contains one row per assessment; take the mean of those
        if avg_row:
            vals = [_float_or_none(r["avg_secs"]) for r in avg_row if _float_or_none(r["avg_secs"]) is not None]
            if vals:
                avg_completion_time_seconds = round(sum(vals) / len(vals), 1)
    except Exception:
        avg_completion_time_seconds = None

    # ------------------------------------------------------------------
    # 4. Status breakdown
    #    completed  = has an assessment_result row
    #    in_progress = no result row yet
    #    abandoned  = 0 (no explicit tracking without a start timestamp)
    # ------------------------------------------------------------------
    status_rows = db.execute(text("""
        SELECT
            COUNT(ar.id) FILTER (WHERE ar.id IS NOT NULL)     AS completed,
            COUNT(a.id)  FILTER (WHERE ar.id IS NULL)         AS in_progress
        FROM assessments a
        LEFT JOIN assessment_results ar ON ar.assessment_id = a.id
    """)).mappings().one()

    status_breakdown = {
        "completed":   _int(status_rows["completed"]),
        "in_progress": _int(status_rows["in_progress"]),
        "abandoned":   0,
    }

    # ------------------------------------------------------------------
    # 5. Assessments by day — last 14 days
    # ------------------------------------------------------------------
    by_day_rows = db.execute(text("""
        SELECT
            DATE(submitted_at AT TIME ZONE 'UTC') AS day,
            COUNT(*) AS cnt
        FROM assessments
        WHERE submitted_at >= :day14_start
        GROUP BY day
        ORDER BY day DESC
    """), {"day14_start": day14_start}).mappings().all()

    by_day_map = {str(r["day"]): _int(r["cnt"]) for r in by_day_rows}

    assessments_by_day = []
    for i in range(13, -1, -1):
        d = (today_start - timedelta(days=i)).date()
        assessments_by_day.append({
            "date":  str(d),
            "count": by_day_map.get(str(d), 0),
        })

    # ------------------------------------------------------------------
    # 6. Top 5 recommended clusters (from JSONB recommended_careers array)
    # ------------------------------------------------------------------
    top_clusters = []
    try:
        cluster_rows = db.execute(text("""
            SELECT
                (elem->>'cluster') AS cluster_name,
                COUNT(*)           AS recommendation_count
            FROM assessment_results res,
            LATERAL jsonb_array_elements(res.recommended_careers) AS elem
            WHERE res.recommended_careers IS NOT NULL
              AND jsonb_typeof(res.recommended_careers) = 'array'
              AND (elem->>'cluster') IS NOT NULL
            GROUP BY cluster_name
            ORDER BY recommendation_count DESC
            LIMIT 5
        """)).mappings().all()
        top_clusters = [
            {
                "cluster_name":       r["cluster_name"],
                "recommendation_count": _int(r["recommendation_count"]),
            }
            for r in cluster_rows
        ]
    except Exception:
        top_clusters = []

    # ------------------------------------------------------------------
    # 7. Assemble response
    # ------------------------------------------------------------------
    return {
        "assessments_today":          assessments_today,
        "assessments_this_week":      assessments_this_week,
        "assessments_total":          assessments_total,
        "avg_completion_time_seconds": avg_completion_time_seconds,
        "results_generated_today":    results_generated_today,
        "scoring_errors_today":       0,
        "scoring_config_version":     SCORING_CONFIG_VERSION,
        "last_assessment_at":         last_assessment_at,
        "assessments_by_day":         assessments_by_day,
        "status_breakdown":           status_breakdown,
        "top_clusters":               top_clusters,
    }
