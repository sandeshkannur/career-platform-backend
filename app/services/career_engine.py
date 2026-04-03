from typing import List, Dict, Any
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app import models
from app.services.scoring import compute_career_scores, compute_career_scores_v2


def compute_careers_for_student(
    student_id: int,
    db: Session,
    *,
    assessment_id: int | None = None,
    limit: int = 368,
    include_explainability: bool = True,
    include_keyskills: bool = True,
    include_clusters: bool = True,
) -> List[Dict[str, Any]]:
    """
    Single source of truth for career computation.

    IMPORTANT:
    - No language selection here.
    - No premium/free gating here.
    - No request context here.
    """

    # 1) Validate student has keyskills
    keyskill_rows = (
        db.query(models.StudentKeySkillMap.keyskill_id)
        .filter_by(student_id=student_id)
        .all()
    )
    if not keyskill_rows:
        raise HTTPException(status_code=404, detail="No keyskills found for this student")

    # 2) Compute career scores — v2 if career_student_skill has data and
    #    assessment_id is available, otherwise fall back to v1.
    use_v2 = False
    if assessment_id is not None:
        has_css = db.execute(text("SELECT 1 FROM career_student_skill LIMIT 1")).first()
        use_v2 = has_css is not None

    if use_v2:
        career_scores = compute_career_scores_v2(
            student_id=student_id,
            assessment_id=assessment_id,
            db=db,
        )
    else:
        career_scores = compute_career_scores(db, student_id)
    if not career_scores:
        raise HTTPException(
            status_code=404,
            detail="No career scores could be computed for this student",
        )

    # 3) Pick Top N careers by score (only >0)
    top = [
        (cid, s)
        for cid, s in sorted(career_scores.items(), key=lambda x: x[1], reverse=True)
        if s > 0
    ][:limit]
    top_career_ids = [cid for cid, _ in top]

    if not top_career_ids:
        return []

    # 4) Explainability: top contributing keyskills (by effective weight)
    contrib_by_career: dict[int, list] = {}

    if include_keyskills or include_explainability:
        contrib_rows = db.execute(
            text(
                """
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
                  ON v.keyskill_id = k.id
                WHERE skm.student_id = :sid
                  AND v.career_id = ANY(:career_ids)
                ORDER BY v.career_id, v.effective_weight_int DESC, v.keyskill_code
                """
            ),
            {"sid": student_id, "career_ids": top_career_ids},
        ).mappings().all()

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

    # 5) Load Career rows for selected IDs
    careers = (
        db.query(models.Career)
        .filter(models.Career.id.in_(top_career_ids))
        .all()
    )
    career_by_id = {c.id: c for c in careers}

    # 6) Build stable output shape (matches what you already persist/return)
    out: List[Dict[str, Any]] = []

    for cid, score in top:
        c = career_by_id.get(cid)
        if not c:
            continue

        obj: Dict[str, Any] = {
            "career_id": c.id,
            "career_code": c.career_code,
            "title": c.title,
            "description": c.description,
        }

        if include_clusters:
            obj["cluster"] = c.cluster.name if c.cluster else None

        # Keep score present for admin paths; student-safe sanitization removes it.
        obj["score"] = score
        # Compute fit_band_key based on score (student-safe label, no numbers)
        if score >= 90:
            fit_band_key = 'high_potential'
        elif score >= 75:
            fit_band_key = 'strong'
        elif score >= 60:
            fit_band_key = 'promising'
        elif score >= 45:
            fit_band_key = 'developing'
        else:
            fit_band_key = 'exploring'
        obj['fit_band_key'] = fit_band_key


        if include_keyskills:
            obj["matched_keyskills"] = contrib_by_career.get(c.id, [])

        if include_explainability:
            obj["explainability"] = [
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
            ]

        out.append(obj)

    return out