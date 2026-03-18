# backend/app/services/scoring.py

from sqlalchemy.orm import Session
from sqlalchemy import select, text
from app import models
from sqlalchemy.exc import ProgrammingError


def get_student_keyskill_scores(db: Session, student_id: int) -> dict:
    """
    Returns {keyskill_id: normalized_score} for a given student.

    Preferred behavior:
    - Uses StudentKeySkillMap.score if present:
        * score is assumed to be 0–100 (from assessment engine)
        * we normalize to 0.0–1.0

    Fallback behavior:
    - If the live DB does not yet have student_keyskill_map.score,
      treat the existence of a mapping row as legacy binary strength = 1.0
    """

    try:
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
                # Legacy behavior: presence = full strength
                normalized = 1.0
            else:
                value = float(raw_score)

                # Mixed-scale support:
                # - if value is 0–1, treat as already-normalized
                # - if value is >1, treat as 0–100 and normalize
                if value <= 1.0:
                    normalized = max(0.0, min(1.0, value))
                else:
                    value_0_100 = max(0.0, min(100.0, value))
                    normalized = value_0_100 / 100.0

            scores[keyskill_id] = normalized

        return scores

    except ProgrammingError:
        db.rollback()

        # Fallback for older/live schema where `score` column is absent:
        # presence of student_keyskill_map row = full strength
        rows = db.execute(
            select(
                models.StudentKeySkillMap.keyskill_id,
            ).where(
                models.StudentKeySkillMap.student_id == student_id
            )
        ).all()

        return {keyskill_id: 1.0 for (keyskill_id,) in rows}


def compute_career_scores(db: Session, student_id: int) -> dict:
    """
    Weighted scoring:
        score = Σ(student_keyskill_score * weight_percentage)

    - student_keyskill_score is 0.0–1.0
    - weight_percentage is e.g. 35, 25, 10...
    → max score per career remains 100.
    """
    student_scores = get_student_keyskill_scores(db, student_id)

    try:
        rows = db.execute(
            text("""
                SELECT
                    career_id,
                    keyskill_id,
                    effective_weight_int AS weight_percentage
                FROM career_keyskill_weights_effective_int_v
            """)
        ).all()

    except ProgrammingError:
        # Clear failed transaction state before continuing
        db.rollback()

        # Fallback when the view doesn't exist (local/dev)
        rows = db.execute(
            text("""
                SELECT
                    career_id,
                    keyskill_id,
                    COALESCE(weight_percentage, 0) AS weight_percentage
                FROM career_keyskill_association
            """)
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
