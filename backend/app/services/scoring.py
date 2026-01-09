# backend/app/services/scoring.py

from sqlalchemy.orm import Session
from sqlalchemy import select
from app import models


def get_student_keyskill_scores(db: Session, student_id: int) -> dict:
    """
    Returns {keyskill_id: normalized_score} for a given student.

    - Uses StudentKeySkillMap.score if present:
        * score is assumed to be 0–100 (from assessment engine)
        * we normalize to 0.0–1.0
    - If score is NULL, we treat it as 100 → 1.0 (legacy binary behavior).
    """

    rows = db.execute(
        select(
            models.StudentKeySkillMap.keyskill_id,
            models.StudentKeySkillMap.score,
        ).where(
            models.StudentKeySkillMap.student_id == student_id
        )
    ).all()

    scores: dict[int, float] = {}

    for keyskill_id, raw_score in rows:
        if raw_score is None:
            # Old behavior: presence = full strength
            normalized = 1.0
        else:
            # Clamp to [0, 100] just in case and normalize
            value = max(0.0, min(100.0, float(raw_score)))
            normalized = value / 100.0

        scores[keyskill_id] = normalized

    return scores


def compute_career_scores(db: Session, student_id: int) -> dict:
    """
    Weighted scoring:
        score = Σ(student_keyskill_score * weight_percentage)

    - student_keyskill_score is 0.0–1.0
    - weight_percentage is e.g. 35, 25, 10...
    → max score per career remains 100.
    """
    student_scores = get_student_keyskill_scores(db, student_id)

    rows = db.execute(
        select(
            models.career_keyskill_association.c.career_id,
            models.career_keyskill_association.c.keyskill_id,
            models.career_keyskill_association.c.weight_percentage,
        )
    ).all()

    career_scores: dict[int, float] = {}

    for career_id, keyskill_id, weight in rows:
        if career_id not in career_scores:
            career_scores[career_id] = 0.0

        s_val = student_scores.get(keyskill_id, 0.0)
        career_scores[career_id] += s_val * float(weight)

    return {cid: round(score, 2) for cid, score in career_scores.items()}


def compute_cluster_scores(db: Session, career_scores: dict) -> dict:
    """
    Cluster score = max(career scores in that cluster)
    """
    rows = db.execute(
        select(models.Career.id, models.Career.cluster_id)
    ).all()

    cluster_career_map: dict[int, list[float]] = {}

    for career_id, cluster_id in rows:
        if cluster_id is None:
            continue
        cluster_career_map.setdefault(cluster_id, [])
        cluster_career_map[cluster_id].append(career_scores.get(career_id, 0.0))

    cluster_scores: dict[int, float] = {}
    for cid, scores in cluster_career_map.items():
        cluster_scores[cid] = round(max(scores), 2) if scores else 0.0

    return cluster_scores
