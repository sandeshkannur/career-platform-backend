# app/routers/recommendations.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app import models
from app.deps import get_db

router = APIRouter(
    prefix="/recommendations",
    tags=["Recommendations"],
    # NOTE: no auth dependency here to avoid 401 issues in Swagger for now
)


@router.get("/recommendations/{student_id}")
def get_recommendations(
    student_id: int,
    db: Session = Depends(get_db),
):
    """
    Get career recommendations for a student based on:

    StudentKeySkillMap -> KeySkill -> Career (via career_keyskill_association)
    """

    # 1) Get student's keyskills from StudentKeySkillMap
    keyskill_rows = (
        db.query(models.StudentKeySkillMap.keyskill_id)
        .filter_by(student_id=student_id)
        .all()
    )

    if not keyskill_rows:
        raise HTTPException(
            status_code=404,
            detail="No keyskills found for this student",
        )

    keyskill_ids = [row[0] for row in keyskill_rows]

    # 2) Get careers linked to those keyskills
    careers = (
        db.query(models.Career)
        .join(models.career_keyskill_association)
        .filter(models.career_keyskill_association.c.keyskill_id.in_(keyskill_ids))
        .distinct()
        .all()
    )

    # 3) Format response
    recommendations = [
        {
            "career_id": c.id,
            "title": c.title,
            "description": c.description,
            "cluster": c.cluster.name if c.cluster else None,
        }
        for c in careers
    ]

    return {
        "student_id": student_id,
        "recommended_careers": recommendations,
    }
