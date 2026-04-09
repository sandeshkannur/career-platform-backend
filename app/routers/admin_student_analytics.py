# app/routers/admin_student_analytics.py
"""
Admin student drill-down analytics endpoint.
Powers the student detail panel inside the Funnel & Students tab.

GET /v1/admin-student-analytics/{student_id}
Auth: require_admin_or_counsellor
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.deps import get_db
from app.auth.auth import require_admin_or_counsellor

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fit_band(score):
    if score is None:
        return "exploring"
    s = float(score)
    if s >= 80:
        return "high_potential"
    if s >= 65:
        return "strong"
    if s >= 50:
        return "promising"
    if s >= 35:
        return "developing"
    return "exploring"


def _cps_interpretation(cps_score, ses_band, education_board):
    if cps_score is None:
        return "No context profile recorded."
    cps = float(cps_score)
    context_filled = all(
        v not in (None, "unknown", "")
        for v in [ses_band, education_board]
    )
    if not context_filled:
        return (
            "Low-resource rural baseline applied. HSI fairness boost active. "
            "Fill context profile for personalised adjustment."
        )
    if cps < 60:
        return f"CPS {cps} — Strong fairness boost applied. Student benefits significantly from HSI adjustment."
    if cps < 75:
        return f"CPS {cps} — Moderate fairness boost applied."
    return f"CPS {cps} — Minimal fairness boost. High-resource context detected."


def _safe_float(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def _safe_str(v):
    return str(v) if v is not None else None


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
    student_row = db.execute(text("""
        SELECT s.id, s.name, s.grade, u.email, u.subscription_tier
        FROM students s
        LEFT JOIN users u ON u.id = s.user_id
        WHERE s.id = :student_id
    """), {"student_id": student_id}).mappings().first()

    if not student_row:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found.")

    student = {
        "id":                int(student_row["id"]),
        "name":              _safe_str(student_row["name"]),
        "grade":             student_row["grade"],
        "email":             _safe_str(student_row["email"]),
        "subscription_tier": _safe_str(student_row["subscription_tier"]),
    }

    # ------------------------------------------------------------------ #
    # Section A — Assessment timeline
    # ------------------------------------------------------------------ #
    section_a = []
    try:
        rows = db.execute(text("""
            SELECT
              a.id AS assessment_id,
              a.submitted_at,
              COUNT(ar.id) AS response_count,
              CASE WHEN res.id IS NOT NULL THEN true ELSE false END AS has_results,
              res.recommended_stream,
              ROUND(AVG(ar.answer_value::numeric), 2)   AS mean_answer,
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
                WHEN STDDEV(ar.answer_value::numeric) < 0.3                        THEN 'straight_liner'
                WHEN AVG(ar.answer_value::numeric) > 4.5                           THEN 'acquiescence_bias'
                WHEN AVG(ar.answer_value::numeric) < 1.5                           THEN 'disacquiescence_bias'
                WHEN AVG(ar.answer_value::numeric) BETWEEN 2.8 AND 3.2
                 AND STDDEV(ar.answer_value::numeric) < 0.5                        THEN 'central_tendency_bias'
                ELSE 'normal'
              END AS pattern
            FROM assessments a
            LEFT JOIN assessment_responses ar ON ar.assessment_id = a.id
            LEFT JOIN assessment_results res  ON res.assessment_id = a.id
            LEFT JOIN students s              ON s.user_id = a.user_id
            WHERE s.id = :student_id
            GROUP BY a.id, a.submitted_at, res.id, res.recommended_stream
            ORDER BY a.submitted_at DESC
        """), {"student_id": student_id}).mappings().all()

        for r in rows:
            section_a.append({
                "assessment_id":      int(r["assessment_id"]),
                "submitted_at":       r["submitted_at"].isoformat() if r["submitted_at"] else None,
                "response_count":     int(r["response_count"] or 0),
                "has_results":        bool(r["has_results"]),
                "recommended_stream": _safe_str(r["recommended_stream"]),
                "pattern":            _safe_str(r["pattern"]),
                "mean_answer":        _safe_float(r["mean_answer"]),
                "stddev_answer":      _safe_float(r["stddev_answer"]),
                "answer_range":       int(r["answer_range"]) if r["answer_range"] is not None else None,
                "cnt_5":              int(r["cnt_5"] or 0),
                "cnt_4":              int(r["cnt_4"] or 0),
                "cnt_3":              int(r["cnt_3"] or 0),
                "cnt_2":              int(r["cnt_2"] or 0),
                "cnt_1":              int(r["cnt_1"] or 0),
            })
    except Exception as e:
        section_a = []
        print(f"[admin_student_analytics] section_a error student={student_id}: {e}")

    # ------------------------------------------------------------------ #
    # Section B — Skill profile
    # ------------------------------------------------------------------ #
    section_b_skill_profile = []
    try:
        rows = db.execute(text("""
            SELECT
              sk.name AS skill,
              ROUND(AVG(sss.hsi_score)::numeric, 2) AS mean_hsi,
              ROUND(MAX(sss.hsi_score)::numeric, 2) AS max_hsi,
              ROUND(MIN(sss.hsi_score)::numeric, 2) AS min_hsi,
              COUNT(DISTINCT sss.assessment_id)     AS assessment_count
            FROM student_skill_scores sss
            LEFT JOIN skills sk ON sk.id = sss.skill_id
            WHERE sss.student_id = :student_id
            GROUP BY sk.name
            ORDER BY mean_hsi DESC
        """), {"student_id": student_id}).mappings().all()

        for r in rows:
            mean = _safe_float(r["mean_hsi"])
            section_b_skill_profile.append({
                "skill":            _safe_str(r["skill"]),
                "mean_hsi":         mean,
                "max_hsi":          _safe_float(r["max_hsi"]),
                "min_hsi":          _safe_float(r["min_hsi"]),
                "assessment_count": int(r["assessment_count"] or 0),
                "fit_band":         _fit_band(mean),
            })
    except Exception as e:
        section_b_skill_profile = []
        print(f"[admin_student_analytics] section_b_skill_profile error student={student_id}: {e}")

    section_b_platform_avg = []
    try:
        rows = db.execute(text("""
            SELECT
              sk.name AS skill,
              ROUND(AVG(sss.hsi_score)::numeric, 2) AS platform_mean
            FROM student_skill_scores sss
            LEFT JOIN skills sk ON sk.id = sss.skill_id
            GROUP BY sk.name
            ORDER BY platform_mean DESC
        """)).mappings().all()

        for r in rows:
            section_b_platform_avg.append({
                "skill":         _safe_str(r["skill"]),
                "platform_mean": _safe_float(r["platform_mean"]),
            })
    except Exception as e:
        section_b_platform_avg = []
        print(f"[admin_student_analytics] section_b_platform_avg error: {e}")

    # ------------------------------------------------------------------ #
    # Section C — Career stability
    # ------------------------------------------------------------------ #
    total_results = sum(1 for a in section_a if a["has_results"])

    stable_careers = []
    unstable_careers = []
    rank1_history = []

    try:
        rows = db.execute(text("""
            SELECT
              elem->>'title'   AS career_title,
              elem->>'cluster' AS cluster,
              COUNT(*)         AS appearances
            FROM assessment_results res
            LEFT JOIN assessments a ON a.id = res.assessment_id
            LEFT JOIN students s    ON s.user_id = a.user_id,
            LATERAL jsonb_array_elements(res.recommended_careers) AS elem
            WHERE s.id = :student_id
              AND res.recommended_careers IS NOT NULL
              AND jsonb_typeof(res.recommended_careers) = 'array'
            GROUP BY elem->>'title', elem->>'cluster'
            ORDER BY appearances DESC
        """), {"student_id": student_id}).mappings().all()

        for r in rows:
            appearances = int(r["appearances"] or 0)
            pct = round(appearances / total_results * 100, 1) if total_results else 0.0
            entry = {
                "career_title":   _safe_str(r["career_title"]),
                "appearances":    appearances,
                "total_results":  total_results,
                "stability_pct":  pct,
            }
            if pct >= 50.0:
                entry["clusters"] = [_safe_str(r["cluster"])] if r["cluster"] else []
                stable_careers.append(entry)
            else:
                unstable_careers.append(entry)
    except Exception as e:
        print(f"[admin_student_analytics] section_c_frequency error student={student_id}: {e}")

    try:
        rows = db.execute(text("""
            SELECT
              a.id            AS assessment_id,
              a.submitted_at,
              elem->>'title'   AS rank1_career,
              elem->>'cluster' AS rank1_cluster
            FROM assessment_results res
            LEFT JOIN assessments a ON a.id = res.assessment_id
            LEFT JOIN students s    ON s.user_id = a.user_id,
            LATERAL jsonb_array_elements(res.recommended_careers)
              WITH ORDINALITY AS t(elem, ord)
            WHERE s.id = :student_id
              AND t.ord = 1
              AND res.recommended_careers IS NOT NULL
              AND jsonb_typeof(res.recommended_careers) = 'array'
            ORDER BY a.submitted_at DESC
        """), {"student_id": student_id}).mappings().all()

        for r in rows:
            rank1_history.append({
                "assessment_id": int(r["assessment_id"]),
                "submitted_at":  r["submitted_at"].isoformat() if r["submitted_at"] else None,
                "rank1_career":  _safe_str(r["rank1_career"]),
                "rank1_cluster": _safe_str(r["rank1_cluster"]),
            })
    except Exception as e:
        print(f"[admin_student_analytics] section_c_rank1 error student={student_id}: {e}")

    section_c = {
        "stable_careers":   stable_careers,
        "unstable_careers": unstable_careers,
        "rank1_history":    rank1_history,
    }

    # ------------------------------------------------------------------ #
    # Section D — Keyskill scores
    # ------------------------------------------------------------------ #
    section_d = []
    try:
        rows = db.execute(text("""
            SELECT ks.name AS keyskill, skm.score
            FROM student_keyskill_map skm
            LEFT JOIN keyskills ks ON ks.id = skm.keyskill_id
            WHERE skm.student_id = :student_id
            ORDER BY skm.score DESC
        """), {"student_id": student_id}).mappings().all()

        for r in rows:
            score = _safe_float(r["score"])
            section_d.append({
                "keyskill": _safe_str(r["keyskill"]),
                "score":    score,
                "fit_band": _fit_band(score),
            })
    except Exception as e:
        section_d = []
        print(f"[admin_student_analytics] section_d error student={student_id}: {e}")

    # ------------------------------------------------------------------ #
    # Section E — Bias flags (assessments with non-normal patterns)
    # ------------------------------------------------------------------ #
    section_e = []
    bias_recommendations = {
        "straight_liner":         "Results from this attempt are unreliable. Student answered identically to all questions. Recommend retake.",
        "acquiescence_bias":      "Student shows strong agreement bias (mean > 4.5). Results may be inflated. Recommend review.",
        "disacquiescence_bias":   "Student shows strong disagreement bias (mean < 1.5). Results may be deflated. Recommend review.",
        "central_tendency_bias":  "Student shows central tendency bias (clustering near midpoint). Discrimination between skills is low. Recommend retake.",
    }
    for entry in section_a:
        pattern = entry.get("pattern")
        if pattern and pattern != "normal":
            section_e.append({
                "assessment_id":  entry["assessment_id"],
                "submitted_at":   entry["submitted_at"],
                "pattern":        pattern,
                "mean_answer":    entry["mean_answer"],
                "stddev_answer":  entry["stddev_answer"],
                "response_count": entry["response_count"],
                "recommendation": bias_recommendations.get(
                    pattern,
                    "Non-standard response pattern detected. Manual review recommended."
                ),
            })

    # ------------------------------------------------------------------ #
    # Section F — Interest inventory
    # ------------------------------------------------------------------ #
    section_f = {
        "completed":    False,
        "completed_at": None,
        "lang":         None,
        "top_clusters": [],
        "cluster_boosts": {},
    }
    try:
        row = db.execute(text("""
            SELECT id, student_id, lang, answers, cluster_boosts,
                   top_clusters, created_at, updated_at
            FROM interest_inventory_responses
            WHERE student_id = :student_id
            ORDER BY created_at DESC
            LIMIT 1
        """), {"student_id": student_id}).mappings().first()

        if row:
            section_f = {
                "completed":      True,
                "completed_at":   row["updated_at"].isoformat() if row["updated_at"] else None,
                "lang":           _safe_str(row["lang"]),
                "top_clusters":   list(row["top_clusters"]) if row["top_clusters"] else [],
                "cluster_boosts": dict(row["cluster_boosts"]) if row["cluster_boosts"] else {},
            }
    except Exception as e:
        print(f"[admin_student_analytics] section_f error student={student_id}: {e}")

    # ------------------------------------------------------------------ #
    # Section G — Context profile
    # ------------------------------------------------------------------ #
    section_g = {
        "assessment_id":     None,
        "ses_band":          None,
        "education_board":   None,
        "support_level":     None,
        "resource_access":   None,
        "cps_score":         None,
        "cps_interpretation": "No context profile recorded.",
        "context_filled":    False,
    }
    try:
        row = db.execute(text("""
            SELECT cp.assessment_id, cp.ses_band, cp.education_board,
                   cp.support_level, cp.resource_access, cp.cps_score
            FROM context_profile cp
            LEFT JOIN assessments a ON a.id = cp.assessment_id
            LEFT JOIN students s    ON s.user_id = a.user_id
            WHERE s.id = :student_id
            ORDER BY a.submitted_at DESC
            LIMIT 1
        """), {"student_id": student_id}).mappings().first()

        if row:
            ses_band       = _safe_str(row["ses_band"])
            education_board = _safe_str(row["education_board"])
            support_level  = _safe_str(row["support_level"])
            resource_access = _safe_str(row["resource_access"])
            cps_score      = _safe_float(row["cps_score"])
            context_filled = all(
                v not in (None, "unknown", "")
                for v in [ses_band, education_board, support_level, resource_access]
            )
            section_g = {
                "assessment_id":      int(row["assessment_id"]),
                "ses_band":           ses_band,
                "education_board":    education_board,
                "support_level":      support_level,
                "resource_access":    resource_access,
                "cps_score":          cps_score,
                "cps_interpretation": _cps_interpretation(cps_score, ses_band, education_board),
                "context_filled":     context_filled,
            }
    except Exception as e:
        print(f"[admin_student_analytics] section_g error student={student_id}: {e}")

    # ------------------------------------------------------------------ #
    # Summary
    # ------------------------------------------------------------------ #
    total_assessments      = len(section_a)
    assessments_with_results = total_results
    assessments_no_results = total_assessments - assessments_with_results

    dominant_career      = None
    dominant_career_pct  = 0.0
    if stable_careers:
        top = stable_careers[0]
        dominant_career     = top["career_title"]
        dominant_career_pct = top["stability_pct"]

    summary = {
        "total_assessments":        total_assessments,
        "assessments_with_results": assessments_with_results,
        "assessments_no_results":   assessments_no_results,
        "bias_flag_count":          len(section_e),
        "dominant_career":          dominant_career,
        "dominant_career_pct":      dominant_career_pct,
        "context_profile_filled":   section_g["context_filled"],
        "interest_inventory_done":  section_f["completed"],
        "keyskills_computed":       len(section_d) > 0,
    }

    return {
        "student":                 student,
        "section_a_timeline":      section_a,
        "section_b_skill_profile": section_b_skill_profile,
        "section_b_platform_avg":  section_b_platform_avg,
        "section_c_career_stability": section_c,
        "section_d_keyskills":     section_d,
        "section_e_bias_flags":    section_e,
        "section_f_interest":      section_f,
        "section_g_context":       section_g,
        "summary":                 summary,
    }
