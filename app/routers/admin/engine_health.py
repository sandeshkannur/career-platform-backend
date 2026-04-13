"""
Scoring engine health dashboard.

  GET /v1/admin/engine/health

Read-only. Admin auth required. No writes, no scoring logic changes.

Resilience design: every query block has its own try/except + db.rollback().
A single failing query (table missing, schema mismatch, etc.) cannot abort
the transaction and poison the remaining queries — each block returns a safe
default independently.
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
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


def _float_or_none(val):
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
    # 1. Assessment counts — today / this week / total / last timestamp
    # ------------------------------------------------------------------
    assessments_today     = 0
    assessments_this_week = 0
    assessments_total     = 0
    last_assessment_at    = None
    try:
        row = db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE submitted_at >= :today)      AS today,
                COUNT(*) FILTER (WHERE submitted_at >= :week_start) AS this_week,
                COUNT(*)                                             AS total,
                MAX(submitted_at)                                    AS last_at
            FROM assessments
        """), {"today": today_start, "week_start": week_start}).mappings().one()

        assessments_today     = _int(row["today"])
        assessments_this_week = _int(row["this_week"])
        assessments_total     = _int(row["total"])
        if row["last_at"] is not None and hasattr(row["last_at"], "isoformat"):
            last_assessment_at = row["last_at"].isoformat()
    except Exception:
        db.rollback()

    # ------------------------------------------------------------------
    # 2. Results generated today
    # ------------------------------------------------------------------
    results_generated_today = 0
    try:
        row = db.execute(text("""
            SELECT COUNT(*) AS cnt
            FROM assessment_results
            WHERE generated_at >= :today
        """), {"today": today_start}).mappings().one()
        results_generated_today = _int(row["cnt"])
    except Exception:
        db.rollback()

    # ------------------------------------------------------------------
    # 3. Avg completion time (seconds)
    #    Proxy: earliest assessment_response.created_at per assessment
    #    as the start time. Null if that column doesn't exist or is empty.
    # ------------------------------------------------------------------
    avg_completion_time_seconds = None
    try:
        avg_rows = db.execute(text("""
            SELECT
                EXTRACT(EPOCH FROM (
                    a.submitted_at - MIN(ar.created_at)
                )) AS secs
            FROM assessments a
            JOIN assessment_responses ar ON ar.assessment_id = a.id
            GROUP BY a.id, a.submitted_at
        """)).mappings().all()
        vals = [
            _float_or_none(r["secs"])
            for r in avg_rows
            if _float_or_none(r["secs"]) is not None and _float_or_none(r["secs"]) >= 0
        ]
        if vals:
            avg_completion_time_seconds = round(sum(vals) / len(vals), 1)
    except Exception:
        db.rollback()

    # ------------------------------------------------------------------
    # 4. Status breakdown
    #    completed   = has an assessment_results row
    #    in_progress = no result row yet
    #    abandoned   = 0 (no start-timestamp tracking exists yet)
    # ------------------------------------------------------------------
    status_breakdown = {"completed": 0, "in_progress": 0, "abandoned": 0}
    try:
        row = db.execute(text("""
            SELECT
                COUNT(ar.id) FILTER (WHERE ar.id IS NOT NULL) AS completed,
                COUNT(a.id)  FILTER (WHERE ar.id IS NULL)     AS in_progress
            FROM assessments a
            LEFT JOIN assessment_results ar ON ar.assessment_id = a.id
        """)).mappings().one()
        status_breakdown = {
            "completed":   _int(row["completed"]),
            "in_progress": _int(row["in_progress"]),
            "abandoned":   0,
        }
    except Exception:
        db.rollback()

    # ------------------------------------------------------------------
    # 5. Assessments by day — last 14 days (always returns 14 entries)
    # ------------------------------------------------------------------
    assessments_by_day = [
        {"date": str((today_start - timedelta(days=i)).date()), "count": 0}
        for i in range(13, -1, -1)
    ]
    try:
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
        assessments_by_day = [
            {"date": entry["date"], "count": by_day_map.get(entry["date"], 0)}
            for entry in assessments_by_day
        ]
    except Exception:
        db.rollback()
        # assessments_by_day already holds the zeroed-out default

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
                "cluster_name":         r["cluster_name"],
                "recommendation_count": _int(r["recommendation_count"]),
            }
            for r in cluster_rows
        ]
    except Exception:
        db.rollback()

    # ------------------------------------------------------------------
    # 7. Assemble response
    # ------------------------------------------------------------------
    return {
        "assessments_today":           assessments_today,
        "assessments_this_week":       assessments_this_week,
        "assessments_total":           assessments_total,
        "avg_completion_time_seconds": avg_completion_time_seconds,
        "results_generated_today":     results_generated_today,
        "scoring_errors_today":        0,
        "scoring_config_version":      SCORING_CONFIG_VERSION,
        "last_assessment_at":          last_assessment_at,
        "assessments_by_day":          assessments_by_day,
        "status_breakdown":            status_breakdown,
        "top_clusters":                top_clusters,
    }
