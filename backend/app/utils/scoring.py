
from sqlalchemy.orm import Session
from app import models
from collections import defaultdict

def compute_skill_scores(assessment_id: int, db: Session) -> dict:
    responses = db.query(models.AssessmentResponse).filter_by(assessment_id=assessment_id).all()
    skill_scores = defaultdict(int)

    for response in responses:
        question = db.query(models.Question).get(response.question_id)
        if question:
            score = int(response.answer or 1)
            skill_scores[question.skill_id] += score * question.weight

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
