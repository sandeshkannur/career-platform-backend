from sqlalchemy.orm import Session
from app import models
from collections import defaultdict

def compute_skill_scores(assessment_id: int, db: Session, dataset_version: str = "v1") -> dict:
    """
    Deterministic scoring:
    Priority 1: question_student_skill_map (many-to-many question -> student skill)
    Fallback: questions.skill_id (legacy single-skill mapping)

    Note: Keeps existing API behavior; dataset_version defaults to 'v1'.
    """
    responses = db.query(models.AssessmentResponse).filter_by(assessment_id=assessment_id).all()
    skill_scores = defaultdict(float)

    for response in responses:
        # Answer is expected to be numeric (e.g. 0/1/2/3). Default to 1 if empty.
        try:
            score = float(response.answer) if response.answer is not None else 1.0
        except Exception:
            score = 1.0

        # ✅ Priority 1: Use question_student_skill_map if present
        mappings = (
            db.query(models.QuestionStudentSkillMap)
              .filter_by(question_id=response.question_id, dataset_version=dataset_version)
              .all()
        )

        if mappings:
            for m in mappings:
                # weight is stored on mapping table
                skill_scores[m.skill_id] += score * float(m.weight)
            continue

        # ✅ Fallback: legacy single-skill mapping on questions table
        question = db.query(models.Question).get(response.question_id)
        if question:
            skill_scores[question.skill_id] += score * float(getattr(question, "weight", 1) or 1)

    return dict(skill_scores)

def assign_tiers(skill_scores: dict) -> dict:
    tiers = {}
    for skill_id, score in skill_scores.items():
        if score >= 8:
            tiers[skill_id] = "High"
        elif score >= 4:
            tiers[skill_id] = "Medium"
        else:
            tiers[skill_id] = "Low"
    return tiers
    
# =========================================================
# Context Profile Score (CPS) — Hybrid Model v1
# =========================================================

def compute_cps_v1(
    *,
    ses_band: str,
    education_board: str,
    support_level: str,
) -> float:
    """
    Compute Context Profile Score (CPS) on a 0–100 scale.

    Deterministic, explainable, versioned.
    No DB access. No side effects.
    """

    # --- Normalization maps (v1 locked) ---

    ses_map = {
        "EWS": 0.40,
        "LIG": 0.55,
        "MIG": 0.75,
        "HIG": 0.90,
    }

    board_map = {
        "State": 0.55,
        "CBSE": 0.75,
        "ICSE": 0.80,
        "International": 0.90,
    }

    support_map = {
        "Low": 0.50,
        "Medium": 0.75,
        "High": 0.95,
    }

    # --- Safe defaults (psychological safety) ---
    ses_score = ses_map.get(ses_band, 0.60)
    board_score = board_map.get(education_board, 0.65)
    support_score = support_map.get(support_level, 0.65)

    # --- Weighted CPS ---
    cps_normalized = (
        (ses_score * 0.40)
        + (board_score * 0.30)
        + (support_score * 0.30)
    )

    # Scale to 0–100
    cps_scaled = round(cps_normalized * 100, 2)

    return cps_scaled