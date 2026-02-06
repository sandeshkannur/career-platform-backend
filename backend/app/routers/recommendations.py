# app/routers/recommendations.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import text

from app import models
from app.deps import get_db
from app.services.scoring import compute_career_scores
from app.auth.auth import get_current_active_user, require_roles
from app.projections.student_safe import project_student_safe

router = APIRouter(
    tags=["Recommendations"],
    # NOTE: no auth dependency here to avoid 401 issues in Swagger for now
)

def _compute_recommendations_payload(student_id: int, db: Session) -> dict:
    """
    Computes RAW recommendations payload (includes numeric fields).
    Do NOT sanitize here. Sanitization is applied only in student endpoint.
    """
    # 1) Get student's keyskills from StudentKeySkillMap
    keyskill_rows = (
        db.query(models.StudentKeySkillMap.keyskill_id)
        .filter_by(student_id=student_id)
        .all()
    )

    if not keyskill_rows:
        raise HTTPException(status_code=404, detail="No keyskills found for this student")

    # 2) Compute career scores (deterministic)
    career_scores = compute_career_scores(db, student_id)
    if not career_scores:
        raise HTTPException(
            status_code=404,
            detail="No career scores could be computed for this student",
        )

    # 3) Pick Top 3 careers by score
    top_n = 3
    top = sorted(career_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    top_career_ids = [cid for cid, _ in top]

    # 3A) Explainability: top contributing keyskills (by effective weight)
    contrib_rows = db.execute(
        text("""
            SELECT
              skm.student_id,
              v.career_id,
              v.career_code,
              v.keyskill_code,
              v.keyskill_name,
              v.effective_weight_int AS weight
            FROM student_keyskill_map skm
            JOIN keyskills k
              ON k.id = skm.keyskill_id
            JOIN career_keyskill_weights_effective_int_v v
              ON v.keyskill_code = k.keyskill_code
            WHERE skm.student_id = :sid
              AND v.career_id = ANY(:career_ids)
            ORDER BY v.career_id, v.effective_weight_int DESC, v.keyskill_code
        """),
        {"sid": student_id, "career_ids": top_career_ids},
    ).mappings().all()

    contrib_by_career: dict[int, list] = {}
    for r in contrib_rows:
        cid = r["career_id"]
        contrib_by_career.setdefault(cid, [])
        if len(contrib_by_career[cid]) < 3:
            contrib_by_career[cid].append(
                {
                    "keyskill_code": r["keyskill_code"],
                    "keyskill_name": r["keyskill_name"],
                    "weight": int(r["weight"]),
                }
            )

    careers = (
        db.query(models.Career)
        .filter(models.Career.id.in_(top_career_ids))
        .all()
    )
    career_by_id = {c.id: c for c in careers}

    recommendations = []
    for cid, score in top:
        c = career_by_id.get(cid)
        if not c:
            continue
        recommendations.append(
            {
                "career_id": c.id,
                "career_code": c.career_code,
                "title": c.title,
                "description": c.description,
                "cluster": c.cluster.name if c.cluster else None,
                "score": score,
                "matched_keyskills": contrib_by_career.get(c.id, []),
                "explainability": [
                    {
                        "key": "CAREER_TOP_MATCH",
                        "vars": {
                            "career_title": c.title,
                            "career_code": c.career_code,
                            "cluster_name": c.cluster.name if c.cluster else None,
                            "score": score,
                        },
                    },
                    {
                        "key": "CAREER_KEYSKILL_ALIGNMENT",
                        "vars": {
                            "top_keyskills": [
                                ks["keyskill_name"]
                                for ks in contrib_by_career.get(c.id, [])
                            ],
                            "top_keyskill_weights": [
                                ks["weight"]
                                for ks in contrib_by_career.get(c.id, [])
                            ],
                        },
                    },
                ],
            }
        )

    return {
        "student_id": student_id,
        "recommended_careers": recommendations,
    }

def _sanitize_recommendations_payload(payload: dict) -> dict:
    """
    Student-safe sanitization:
    - Remove numeric exposure (scores, weights) from any depth.
    - Keep only student-safe semantic fields + explainability keys/vars (non-numeric).
    """

    def strip_numeric(obj):
        # Recursively remove numeric values and known numeric keys
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                key = str(k)

                # Hard block known numeric fields (even if stringified)
                if key in {
                    "score",
                    "weight",
                    "points",
                    "raw_score",
                    "scaled_score",
                    "top_keyskill_weights",
                }:
                    continue

                # Recurse
                vv = strip_numeric(v)

                # If the value is numeric (int/float) or a list of numerics, drop it
                if isinstance(vv, (int, float)):
                    continue
                if isinstance(vv, list) and vv and all(isinstance(x, (int, float)) for x in vv):
                    continue

                cleaned[key] = vv
            return cleaned

        if isinstance(obj, list):
            return [strip_numeric(x) for x in obj]

        return obj

    # 1) Strip numeric fields everywhere
    sanitized = strip_numeric(payload)

    # 2) Defense-in-depth: ensure matched_keyskills entries never include weight
    for career in sanitized.get("recommended_careers", []) or []:
        if "matched_keyskills" in career and isinstance(career["matched_keyskills"], list):
            for ks in career["matched_keyskills"]:
                if isinstance(ks, dict) and "weight" in ks:
                    ks.pop("weight", None)

        # Also protect explainability vars from known numeric keys
        if "explainability" in career and isinstance(career["explainability"], list):
            for ex in career["explainability"]:
                if isinstance(ex, dict) and isinstance(ex.get("vars"), dict):
                    ex["vars"].pop("score", None)
                    ex["vars"].pop("top_keyskill_weights", None)

    return sanitized


@router.get("/{student_id}")
def get_recommendations(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Get career recommendations for a student based on:

    StudentKeySkillMap -> KeySkill -> Career (via career_keyskill_association)
    """
    # Students can only access their own recommendations.
    # In this app, student linkage is via students.user_id (see /v1/auth/me).
    if current_user.role == "student":
        student_row = (
            db.query(models.Student)
            .filter(models.Student.user_id == current_user.id)
            .first()
        )
        if not student_row or student_row.id != student_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation forbidden",
            )
    
    payload = _compute_recommendations_payload(student_id=student_id, db=db)

    # ✅ IMPORTANT: Student endpoint returns sanitized payload only
    return project_student_safe(_sanitize_recommendations_payload(payload))

    

@router.get("/admin/{student_id}")
def get_recommendations_admin(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles("admin", "counsellor")),
):
    # Reuse the same logic by calling the student route function body pattern
    # (We keep it simple: duplicate the call path by invoking the same compute pipeline)
    return _compute_recommendations_payload(student_id=student_id, db=db)
