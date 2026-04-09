# app/routers/admin_analytics.py
"""
Admin-only platform analytics dashboard endpoint.
READ-ONLY — no existing models or services are touched.
All queries use raw SQL via db.execute(text(...)).
"""

from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.deps import get_db
from app.auth.auth import require_admin_or_counsellor

router = APIRouter()


def _f(val):
    """Convert Decimal/None to float, or return None."""
    return float(val) if val is not None else None


def _i(val):
    """Convert to int, defaulting None to 0."""
    return int(val) if val is not None else 0


@router.get("/platform")
def get_platform_analytics(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    error_log = []

    # ── Funnel ────────────────────────────────────────────────────────────────
    funnel = {}
    try:
        row = db.execute(text("""
            SELECT
              (SELECT COUNT(*) FROM assessments) AS total_assessments,
              (SELECT COUNT(*) FROM assessments WHERE submitted_at IS NOT NULL) AS total_submitted,
              (SELECT COUNT(DISTINCT assessment_id) FROM assessment_results) AS total_with_results,
              (SELECT COUNT(DISTINCT assessment_id) FROM student_skill_scores) AS total_with_skill_scores,
              (SELECT COUNT(DISTINCT student_id) FROM student_keyskill_map) AS total_with_keyskill_scores,
              (SELECT COUNT(DISTINCT student_id) FROM interest_inventory_responses) AS total_with_interest_inventory,
              (SELECT COUNT(DISTINCT assessment_id) FROM context_profile) AS total_with_context_profile,
              (SELECT COUNT(*) FROM assessments a
               WHERE NOT EXISTS (SELECT 1 FROM assessment_results r WHERE r.assessment_id = a.id)
              ) AS submitted_no_results,
              (SELECT COUNT(*) FROM (
                SELECT assessment_id FROM assessment_responses
                GROUP BY assessment_id
                HAVING COUNT(*) NOT BETWEEN 45 AND 65
              ) t) AS wrong_response_count,
              (SELECT COUNT(*) FROM assessment_responses WHERE answer_value IS NULL) AS null_answer_values
        """)).mappings().first()
        if row:
            funnel = {
                "total_assessments":           _i(row["total_assessments"]),
                "total_submitted":             _i(row["total_submitted"]),
                "total_with_results":          _i(row["total_with_results"]),
                "total_with_skill_scores":     _i(row["total_with_skill_scores"]),
                "total_with_keyskill_scores":  _i(row["total_with_keyskill_scores"]),
                "total_with_interest_inventory": _i(row["total_with_interest_inventory"]),
                "total_with_context_profile":  _i(row["total_with_context_profile"]),
                "submitted_no_results":        _i(row["submitted_no_results"]),
                "wrong_response_count":        _i(row["wrong_response_count"]),
                "null_answer_values":          _i(row["null_answer_values"]),
            }
    except Exception as e:
        error_log.append(f"funnel: {e}")

    # ── Students ──────────────────────────────────────────────────────────────
    students = []
    try:
        rows = db.execute(text("""
            SELECT
              s.id AS student_id,
              s.name AS student_name,
              s.grade,
              u.email,
              u.subscription_tier,
              COUNT(DISTINCT a.id) AS total_assessments,
              COUNT(DISTINCT res.assessment_id) AS assessments_with_results,
              COUNT(DISTINCT a.id) - COUNT(DISTINCT res.assessment_id) AS assessments_no_results,
              CASE WHEN EXISTS(
                SELECT 1 FROM student_keyskill_map skm WHERE skm.student_id = s.id
              ) THEN true ELSE false END AS has_keyskill_scores,
              CASE WHEN EXISTS(
                SELECT 1 FROM interest_inventory_responses iir WHERE iir.student_id = s.id
              ) THEN true ELSE false END AS has_interest_inventory
            FROM students s
            LEFT JOIN users u ON u.id = s.user_id
            LEFT JOIN assessments a ON a.user_id = s.user_id
            LEFT JOIN assessment_results res ON res.assessment_id = a.id
            GROUP BY s.id, s.name, s.grade, u.email, u.subscription_tier
            ORDER BY s.id
        """)).mappings().all()
        students = [
            {
                "student_id":             _i(r["student_id"]),
                "student_name":           r["student_name"],
                "grade":                  r["grade"],
                "email":                  r["email"],
                "subscription_tier":      r["subscription_tier"],
                "total_assessments":      _i(r["total_assessments"]),
                "assessments_with_results": _i(r["assessments_with_results"]),
                "assessments_no_results": _i(r["assessments_no_results"]),
                "has_keyskill_scores":    bool(r["has_keyskill_scores"]),
                "has_interest_inventory": bool(r["has_interest_inventory"]),
            }
            for r in rows
        ]
    except Exception as e:
        error_log.append(f"students: {e}")

    # ── Response patterns ─────────────────────────────────────────────────────
    response_patterns = []
    try:
        rows = db.execute(text("""
            SELECT
              a.id AS assessment_id,
              s.id AS student_id,
              s.name AS student_name,
              a.submitted_at,
              COUNT(ar.id) AS total_responses,
              ROUND(AVG(ar.answer_value::numeric), 2) AS mean_answer,
              ROUND(STDDEV(ar.answer_value::numeric), 3) AS stddev_answer,
              MIN(ar.answer_value) AS min_val,
              MAX(ar.answer_value) AS max_val,
              MAX(ar.answer_value) - MIN(ar.answer_value) AS answer_range,
              COUNT(*) FILTER(WHERE ar.answer_value = 5) AS cnt_5,
              COUNT(*) FILTER(WHERE ar.answer_value = 4) AS cnt_4,
              COUNT(*) FILTER(WHERE ar.answer_value = 3) AS cnt_3,
              COUNT(*) FILTER(WHERE ar.answer_value = 2) AS cnt_2,
              COUNT(*) FILTER(WHERE ar.answer_value = 1) AS cnt_1,
              CASE
                WHEN STDDEV(ar.answer_value::numeric) < 0.3 THEN 'straight_liner'
                WHEN AVG(ar.answer_value::numeric) > 4.5 THEN 'acquiescence_bias'
                WHEN AVG(ar.answer_value::numeric) < 1.5 THEN 'disacquiescence_bias'
                WHEN AVG(ar.answer_value::numeric) BETWEEN 2.8 AND 3.2
                  AND STDDEV(ar.answer_value::numeric) < 0.5 THEN 'central_tendency_bias'
                ELSE 'normal'
              END AS pattern
            FROM assessment_responses ar
            JOIN assessments a ON a.id = ar.assessment_id
            LEFT JOIN students s ON s.user_id = a.user_id
            GROUP BY a.id, s.id, s.name, a.submitted_at
            ORDER BY stddev_answer ASC
        """)).mappings().all()
        response_patterns = [
            {
                "assessment_id":   _i(r["assessment_id"]),
                "student_id":      _i(r["student_id"]) if r["student_id"] is not None else None,
                "student_name":    r["student_name"],
                "submitted_at":    r["submitted_at"].isoformat() if r["submitted_at"] else None,
                "total_responses": _i(r["total_responses"]),
                "mean_answer":     _f(r["mean_answer"]),
                "stddev_answer":   _f(r["stddev_answer"]),
                "min_val":         r["min_val"],
                "max_val":         r["max_val"],
                "answer_range":    r["answer_range"],
                "cnt_5":           _i(r["cnt_5"]),
                "cnt_4":           _i(r["cnt_4"]),
                "cnt_3":           _i(r["cnt_3"]),
                "cnt_2":           _i(r["cnt_2"]),
                "cnt_1":           _i(r["cnt_1"]),
                "pattern":         r["pattern"],
            }
            for r in rows
        ]
    except Exception as e:
        error_log.append(f"response_patterns: {e}")

    # ── Skill stats ───────────────────────────────────────────────────────────
    skill_stats = []
    overflow_hsi_count = 0
    zero_hsi_count = 0
    try:
        rows = db.execute(text("""
            SELECT
              sk.name AS skill,
              ROUND(AVG(sss.hsi_score)::numeric, 2) AS mean_hsi,
              ROUND(STDDEV(sss.hsi_score)::numeric, 2) AS std_hsi,
              ROUND(MIN(sss.hsi_score)::numeric, 2) AS min_hsi,
              ROUND(MAX(sss.hsi_score)::numeric, 2) AS max_hsi,
              COUNT(*) FILTER(WHERE sss.hsi_score > 100) AS overflow_count,
              COUNT(*) FILTER(WHERE sss.hsi_score = 0) AS zero_count,
              COUNT(DISTINCT sss.assessment_id) AS assessment_count
            FROM student_skill_scores sss
            LEFT JOIN skills sk ON sk.id = sss.skill_id
            GROUP BY sk.name
            ORDER BY mean_hsi DESC
        """)).mappings().all()
        skill_stats = [
            {
                "skill":            r["skill"],
                "mean_hsi":         _f(r["mean_hsi"]),
                "std_hsi":          _f(r["std_hsi"]),
                "min_hsi":          _f(r["min_hsi"]),
                "max_hsi":          _f(r["max_hsi"]),
                "overflow_count":   _i(r["overflow_count"]),
                "zero_count":       _i(r["zero_count"]),
                "assessment_count": _i(r["assessment_count"]),
            }
            for r in rows
        ]
        overflow_hsi_count = sum(r["overflow_count"] for r in skill_stats)
        zero_hsi_count = sum(r["zero_count"] for r in skill_stats)
    except Exception as e:
        error_log.append(f"skill_stats: {e}")

    # ── Career frequency ──────────────────────────────────────────────────────
    career_frequency = []
    try:
        rows = db.execute(text("""
            SELECT
              (elem->>'title') AS career_title,
              (elem->>'cluster') AS cluster,
              COUNT(*) AS count
            FROM assessment_results res,
            LATERAL jsonb_array_elements(res.recommended_careers) AS elem
            WHERE res.recommended_careers IS NOT NULL
              AND jsonb_typeof(res.recommended_careers) = 'array'
            GROUP BY (elem->>'title'), (elem->>'cluster')
            ORDER BY count DESC
            LIMIT 50
        """)).mappings().all()
        career_frequency = [
            {"career_title": r["career_title"], "cluster": r["cluster"], "count": _i(r["count"])}
            for r in rows
        ]
    except Exception as e:
        error_log.append(f"career_frequency: {e}")

    # ── Career tier stats ─────────────────────────────────────────────────────
    career_tier_stats = []
    try:
        rows = db.execute(text("""
            SELECT
              career_tier,
              is_active,
              COUNT(*) AS count
            FROM careers
            GROUP BY career_tier, is_active
            ORDER BY career_tier, is_active DESC
        """)).mappings().all()
        career_tier_stats = [
            {
                "career_tier": r["career_tier"],
                "is_active":   bool(r["is_active"]),
                "count":       _i(r["count"]),
            }
            for r in rows
        ]
    except Exception as e:
        error_log.append(f"career_tier_stats: {e}")

    # ── Rank 1 careers ────────────────────────────────────────────────────────
    rank1_careers = []
    try:
        rows = db.execute(text("""
            SELECT
              (elem->>'title') AS career_title,
              COUNT(*) AS count
            FROM assessment_results res,
            LATERAL jsonb_array_elements(res.recommended_careers) WITH ORDINALITY AS t(elem, ord)
            WHERE res.recommended_careers IS NOT NULL
              AND jsonb_typeof(res.recommended_careers) = 'array'
              AND t.ord = 1
            GROUP BY (elem->>'title')
            ORDER BY count DESC
            LIMIT 20
        """)).mappings().all()
        rank1_careers = [
            {"career_title": r["career_title"], "count": _i(r["count"])}
            for r in rows
        ]
    except Exception as e:
        error_log.append(f"rank1_careers: {e}")

    # ── Cluster distribution ──────────────────────────────────────────────────
    cluster_distribution = []
    try:
        rows = db.execute(text("""
            SELECT
              (elem->>'cluster') AS cluster,
              COUNT(*) AS count
            FROM assessment_results res,
            LATERAL jsonb_array_elements(res.recommended_careers) AS elem
            WHERE res.recommended_careers IS NOT NULL
              AND jsonb_typeof(res.recommended_careers) = 'array'
            GROUP BY (elem->>'cluster')
            ORDER BY count DESC
        """)).mappings().all()
        cluster_distribution = [
            {"cluster": r["cluster"], "count": _i(r["count"])}
            for r in rows
        ]
    except Exception as e:
        error_log.append(f"cluster_distribution: {e}")

    # ── Stream distribution ───────────────────────────────────────────────────
    stream_distribution = []
    try:
        rows = db.execute(text("""
            SELECT recommended_stream AS stream, COUNT(*) AS count
            FROM assessment_results
            WHERE recommended_stream IS NOT NULL
            GROUP BY recommended_stream
            ORDER BY count DESC
        """)).mappings().all()
        stream_distribution = [
            {"stream": r["stream"], "count": _i(r["count"])}
            for r in rows
        ]
    except Exception as e:
        error_log.append(f"stream_distribution: {e}")

    # ── Careers per assessment ────────────────────────────────────────────────
    careers_per_assessment = []
    try:
        rows = db.execute(text("""
            SELECT
              jsonb_array_length(recommended_careers) AS career_count,
              COUNT(*) AS assessment_count
            FROM assessment_results
            WHERE recommended_careers IS NOT NULL
              AND jsonb_typeof(recommended_careers) = 'array'
            GROUP BY jsonb_array_length(recommended_careers)
            ORDER BY career_count DESC
        """)).mappings().all()
        careers_per_assessment = [
            {"career_count": _i(r["career_count"]), "assessment_count": _i(r["assessment_count"])}
            for r in rows
        ]
    except Exception as e:
        error_log.append(f"careers_per_assessment: {e}")

    # ── Keyskill scores ───────────────────────────────────────────────────────
    keyskill_scores = []
    try:
        rows = db.execute(text("""
            SELECT
              skm.student_id,
              s.name AS student_name,
              ks.name AS keyskill,
              skm.score
            FROM student_keyskill_map skm
            LEFT JOIN keyskills ks ON ks.id = skm.keyskill_id
            LEFT JOIN students s ON s.id = skm.student_id
            ORDER BY skm.student_id, ks.name
        """)).mappings().all()
        keyskill_scores = [
            {
                "student_id":   _i(r["student_id"]),
                "student_name": r["student_name"],
                "keyskill":     r["keyskill"],
                "score":        _f(r["score"]),
            }
            for r in rows
        ]
    except Exception as e:
        error_log.append(f"keyskill_scores: {e}")

    # ── CPS stats ─────────────────────────────────────────────────────────────
    cps_stats = {}
    try:
        row = db.execute(text("""
            SELECT
              ROUND(AVG(cps_score_used)::numeric, 2) AS mean,
              ROUND(STDDEV(cps_score_used)::numeric, 4) AS std,
              MIN(cps_score_used) AS min,
              MAX(cps_score_used) AS max
            FROM student_skill_scores
            WHERE cps_score_used IS NOT NULL
        """)).mappings().first()
        if row:
            cps_std = _f(row["std"]) or 0.0
            cps_stats = {
                "mean":      _f(row["mean"]),
                "std":       cps_std,
                "min":       _f(row["min"]),
                "max":       _f(row["max"]),
                "is_locked": cps_std == 0.0 and row["mean"] is not None,
            }
    except Exception as e:
        error_log.append(f"cps_stats: {e}")

    # ── Data issues (computed from query results) ─────────────────────────────
    data_issues = []

    submitted_no_results = funnel.get("submitted_no_results", 0)
    total_with_results   = funnel.get("total_with_results", 0)

    if overflow_hsi_count > 0:
        data_issues.append({
            "severity": "critical",
            "code":     "HSI_OVERFLOW",
            "title":    f"{overflow_hsi_count} skill scores exceed 100",
            "detail":   "HSI formula produces scores above 100. Cap is missing in scoring pipeline.",
            "fix":      "Apply min(100, hsi_score) in scoring service",
        })

    if cps_stats.get("is_locked") and cps_stats.get("mean") is not None:
        data_issues.append({
            "severity": "critical",
            "code":     "CPS_LOCKED",
            "title":    f"CPS locked at {cps_stats['mean']} for all assessments",
            "detail":   "All assessments use identical CPS value. HSI fairness layer is not personalised.",
            "fix":      "Investigate context_profile population. ses_band/education_board may be defaulting.",
        })

    snapshot_368 = next(
        (r["assessment_count"] for r in careers_per_assessment if r["career_count"] == 368), 0
    )
    if snapshot_368 > 0:
        data_issues.append({
            "severity": "critical",
            "code":     "CAREER_SNAPSHOT_BUG",
            "title":    f"368 careers stored in results (should be 9)",
            "detail":   f"{snapshot_368} assessments have career_count=368. Full catalog is being dumped instead of top 9.",
            "fix":      "Fix limit parameter in assessment submit pipeline career snapshot.",
        })

    # Check for null scores in recommended_careers JSONB
    try:
        null_score_row = db.execute(text("""
            SELECT COUNT(*) AS cnt
            FROM assessment_results res,
            LATERAL jsonb_array_elements(res.recommended_careers) AS elem
            WHERE res.recommended_careers IS NOT NULL
              AND jsonb_typeof(res.recommended_careers) = 'array'
              AND (elem->>'score') IS NULL
        """)).mappings().first()
        null_score_count = _i(null_score_row["cnt"]) if null_score_row else 0
        if null_score_count > 0:
            data_issues.append({
                "severity": "info",
                "code":     "NO_SCORE_IN_RESULTS",
                "title":    "Career scores stored in contrib_trace (not recommended_careers)",
                "detail":   (
                    "By design, recommended_careers is student-safe (no scores). "
                    "Admin scores are in contrib_trace.career_scores for assessments after Fix 3 deployment. "
                    "Historical rows have no score stored."
                ),
                "fix":      "Include score and fit_band in the JSONB at scoring time.",
            })
    except Exception as e:
        error_log.append(f"null_score_check: {e}")

    if submitted_no_results > 0:
        data_issues.append({
            "severity": "critical",
            "code":     "MISSING_RESULTS",
            "title":    f"{submitted_no_results} of {submitted_no_results + total_with_results} assessments have no results",
            "detail":   "Many assessments submitted with 0 responses. No validation gate exists.",
            "fix":      "Add minimum response count validation before allowing submit.",
        })

    # Dominant rank-1 career (> 50% of results)
    if rank1_careers and total_with_results > 0:
        top_rank1 = rank1_careers[0]
        if top_rank1["count"] / total_with_results > 0.5:
            data_issues.append({
                "severity": "warning",
                "code":     "DOMINANT_CAREER",
                "title":    f'"{top_rank1["career_title"]}" appears as #1 in {top_rank1["count"]}/{total_with_results} results',
                "detail":   "A single career dominates rank-1. May indicate scoring imbalance.",
                "fix":      "Review career weight distribution or cluster diversity reranker.",
            })

    # ── Resolved issues registry with live verification ──────────────────────
    resolved_issues = [
        {
            "code":       "HSI_OVERFLOW",
            "severity":   "resolved",
            "title":      "21 skill scores exceeded 100 — capped at 100.0",
            "detail":     "HSI formula produced scores above 100. Cap applied in compute_hsi_v1. 21 historical rows backfilled.",
            "fix_applied": "min(100.0, raw * multiplier) in scoring service + SQL backfill of 21 rows",
            "fixed_on":   "2026-04-09",
            "verified":   True,
            "verification": "SELECT COUNT(*) FROM student_skill_scores WHERE hsi_score > 100 → 0 rows",
        },
        {
            "code":       "CAREER_SNAPSHOT_BUG",
            "severity":   "resolved",
            "title":      "368 careers stored in results — reduced to 9",
            "detail":     "26 assessments had full catalog stored instead of top 9. All 3 write sites confirmed at limit=9. Historical rows truncated.",
            "fix_applied": "limit=9 confirmed at all write sites + SQL backfill of 26 rows",
            "fixed_on":   "2026-04-09",
            "verified":   True,
            "verification": "SELECT COUNT(*) FROM assessment_results WHERE jsonb_array_length(recommended_careers) > 9 → 0 rows",
        },
        {
            "code":       "MISSING_RESULTS_GATE",
            "severity":   "resolved",
            "title":      "No response count validation on submit — gate added",
            "detail":     "Assessments could be submitted with 0 responses. Minimum 45-response gate now enforced.",
            "fix_applied": "POST /assessments/{id}/submit rejects 422 INSUFFICIENT_RESPONSES if response_count < 45",
            "fixed_on":   "2026-04-09",
            "verified":   True,
            "verification": "Submit with 0 responses → 422 INSUFFICIENT_RESPONSES confirmed",
        },
        {
            "code":       "CPS_DEFAULTS",
            "severity":   "resolved",
            "title":      "CPS unknown defaults set to low-resource rural baseline",
            "detail":     "All-unknown CPS was 69.5. Lowered to 58.75 to give rural students stronger HSI fairness boost.",
            "fix_applied": "ses=0.55, board=0.70, support=0.55, resource=0.55 in compute_cps_v1",
            "fixed_on":   "2026-04-09",
            "verified":   True,
            "verification": "New assessments with all-unknown context → CPS = 58.75",
        },
        {
            "code":       "ORPHAN_SKILLS",
            "severity":   "resolved",
            "title":      "7 orphan skills zeroed — Education/Health Sci now reachable",
            "detail":     "7 skills held 25-29% dead weight per cluster. Zeroed and 1,635 rows rescaled. Education now top cluster.",
            "fix_applied": "career_student_skill weight=0 for 7 skills + proportional rescale of 1,635 rows",
            "fixed_on":   "2026-04-09",
            "verified":   True,
            "verification": "SELECT SUM(weight) FROM career_student_skill WHERE student_skill IN (...orphans...) → 0.00",
        },
        {
            "code":       "INAPPROPRIATE_CAREERS",
            "severity":   "resolved",
            "title":      "33 inappropriate careers deactivated from recommendations",
            "detail":     "Manual labour, culturally stigmatised, and Western-irrelevant careers removed. Active careers: 368 → 335. 14 careers relabelled for Indian context.",
            "fix_applied": "is_active=FALSE for 33 careers + career_tier classification + scoring engine filters WHERE is_active=TRUE",
            "fixed_on":   "2026-04-09",
            "verified":   True,
            "verification": "SELECT COUNT(*) FROM careers WHERE is_active=TRUE → 335",
        },
    ]

    # Live verification — confirm resolved issues are still clean
    try:
        hsi_check = db.execute(text(
            "SELECT COUNT(*) as cnt FROM student_skill_scores WHERE hsi_score > 100"
        )).fetchone()
        resolved_issues[0]["still_resolved"] = (hsi_check.cnt == 0)
        resolved_issues[0]["live_check"] = f"hsi_score > 100: {hsi_check.cnt} rows"
    except Exception:
        resolved_issues[0]["still_resolved"] = None

    try:
        career_check = db.execute(text(
            "SELECT COUNT(*) as cnt FROM assessment_results WHERE jsonb_array_length(recommended_careers) > 9"
        )).fetchone()
        resolved_issues[1]["still_resolved"] = (career_check.cnt == 0)
        resolved_issues[1]["live_check"] = f"careers > 9: {career_check.cnt} rows"
    except Exception:
        resolved_issues[1]["still_resolved"] = None

    try:
        orphan_check = db.execute(text("""
            SELECT ROUND(SUM(weight)::numeric, 2) AS total
            FROM career_student_skill
            WHERE student_skill IN (
                'Leadership Skills','Technology Literacy','Research Skills',
                'Self-Awareness & Emotional Intelligence','Civic Literacy',
                'Media Literacy','Cultural Literacy'
            )
        """)).fetchone()
        resolved_issues[4]["still_resolved"] = (float(orphan_check.total or 0) == 0.0)
        resolved_issues[4]["live_check"] = f"orphan skill total weight: {orphan_check.total}"
    except Exception:
        resolved_issues[4]["still_resolved"] = None

    try:
        career_count = db.execute(text(
            "SELECT COUNT(*) as cnt FROM careers WHERE is_active = TRUE"
        )).fetchone()
        resolved_issues[5]["still_resolved"] = (career_count.cnt <= 342)
        resolved_issues[5]["live_check"] = f"active careers: {career_count.cnt}"
    except Exception:
        resolved_issues[5]["still_resolved"] = None

    return {
        "generated_at":          datetime.utcnow().isoformat(),
        "funnel":                 funnel,
        "students":               students,
        "response_patterns":      response_patterns,
        "skill_stats":            skill_stats,
        "career_frequency":       career_frequency,
        "career_tier_stats":      career_tier_stats,
        "rank1_careers":          rank1_careers,
        "cluster_distribution":   cluster_distribution,
        "stream_distribution":    stream_distribution,
        "careers_per_assessment": careers_per_assessment,
        "keyskill_scores":        keyskill_scores,
        "cps_stats":              cps_stats,
        "overflow_hsi_count":     overflow_hsi_count,
        "zero_hsi_count":         zero_hsi_count,
        "data_issues":            data_issues,
        "resolved_issues":        resolved_issues,
        **({"error_log": error_log} if error_log else {}),
    }
