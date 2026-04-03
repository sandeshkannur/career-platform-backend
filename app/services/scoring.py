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


def compute_career_scores_v2(student_id: int, assessment_id: int, db: Session) -> dict:
    """
    Sprint1: Score all careers using career_student_skill weights.

    Flow:
    1. Load student_skill_scores.scaled_0_100 for this assessment, normalise to 0–1.
    2. Map skill_id → student_skill_name via skills.student_skill_name.
       If multiple skills map to the same student_skill_name, take the highest score.
    3. For each (career_id, student_skill, weight) in career_student_skill:
       career_score += (student_skill_score_0_1) × weight
       where weight is a percentage (0–100), so max career_score = 100.
    4. Return {career_id: float} — all careers with score > 0.

    Backward compatibility: compute_career_scores (v1) is unchanged.
    """
    # 1) Load skill scores for this assessment
    skill_rows = db.execute(
        select(
            models.StudentSkillScore.skill_id,
            models.StudentSkillScore.scaled_0_100,
        ).where(models.StudentSkillScore.assessment_id == assessment_id)
    ).all()

    if not skill_rows:
        return {}

    # skill_id -> normalised score (0..1)
    raw_skill_scores: dict[int, float] = {
        int(r[0]): max(0.0, min(100.0, float(r[1]))) / 100.0
        for r in skill_rows
        if r[1] is not None
    }

    # 2) Map skill_id -> student_skill_name
    skill_name_rows = db.execute(
        select(models.Skill.id, models.Skill.student_skill_name)
        .where(models.Skill.id.in_(list(raw_skill_scores.keys())))
        .where(models.Skill.student_skill_name.isnot(None))
    ).all()

    # student_skill_name -> best (max) score across all mapped skills
    student_skill_scores: dict[str, float] = {}
    for skill_id, student_skill_name in skill_name_rows:
        score = raw_skill_scores.get(int(skill_id), 0.0)
        existing = student_skill_scores.get(student_skill_name, 0.0)
        if score > existing:
            student_skill_scores[student_skill_name] = score

    if not student_skill_scores:
        return {}

    # 3) Load career_student_skill weights and compute scores
    weight_rows = db.execute(
        text("SELECT career_id, student_skill, weight FROM career_student_skill")
    ).all()

    career_scores: dict[int, float] = {}
    for career_id, student_skill, weight in weight_rows:
        cid = int(career_id)
        w = float(weight)
        s = student_skill_scores.get(str(student_skill), 0.0)

        if cid not in career_scores:
            career_scores[cid] = 0.0

        career_scores[cid] += s * w  # s in 0..1, w in 0..100 → result in 0..100

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
