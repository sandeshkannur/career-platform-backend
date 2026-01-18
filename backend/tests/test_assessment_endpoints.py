# tests/test_assessment_endpoints.py

import pytest
from sqlalchemy.orm import Session
from fastapi import status

from app import models
from app.database import SessionLocal


def test_create_and_get_assessment_happy_path(client, student_token):
    # Arrange
    headers = {"Authorization": f"Bearer {student_token}"}

    # Act: create a new assessment
    resp1 = client.post("/v1/assessments", headers=headers)
    assert resp1.status_code == status.HTTP_201_CREATED
    body1 = resp1.json()
    assert "id" in body1
    assessment_id = body1["id"]

    # Assert: persisted in DB
    db: Session = SessionLocal()
    ass = db.query(models.Assessment).get(assessment_id)
    db.close()
    assert ass is not None
    assert ass.user_id is not None

    # Act: fetch via GET
    resp2 = client.get(f"/v1/assessments/{assessment_id}", headers=headers)
    assert resp2.status_code == status.HTTP_200_OK
    body2 = resp2.json()
    assert body2["id"] == assessment_id
    assert "submitted_at" in body2


def test_submit_responses_and_fetch_result_happy_path(client, student_token):
    # Arrange
    headers = {"Authorization": f"Bearer {student_token}"}

    db = SessionLocal()

    # ---------------------------------------------------------------------
    # NOTE:
    # Your result generation pipeline writes to student_keyskill_map using a
    # student_id that is expected to exist in the `students` table.
    #
    # In your current setup, that student_id ends up being 1, so we ensure
    # the required Student row exists (id=1) to satisfy FK constraints.
    # ---------------------------------------------------------------------
    existing_student = db.query(models.Student).get(1)
    if existing_student is None:
        student = models.Student(id=1, name="Test Student", grade=10)
        db.add(student)
        db.commit()

    # 1) Seed a skill (required for question -> skill mapping & scoring)
    skill = models.Skill(name="Logical Thinking")
    db.add(skill)
    db.commit()
    db.refresh(skill)

    # 2) Seed real questions linked to the skill
    q1 = models.Question(
        id=1,
        assessment_version="v1",
        question_text_en="Test question 1 (EN)",
        question_text_hi="Test question 1 (HI)",
        question_text_ta="Test question 1 (TA)",
        skill_id=skill.id,
        weight=1,
    )
    q2 = models.Question(
        id=2,
        assessment_version="v1",
        question_text_en="Test question 2 (EN)",
        question_text_hi="Test question 2 (HI)",
        question_text_ta="Test question 2 (TA)",
        skill_id=skill.id,
        weight=1,
    )
    db.add_all([q1, q2])
    db.commit()

    # 3) Seed an assessment directly (fast setup)
    ass = models.Assessment(user_id=1)
    db.add(ass)
    db.commit()
    db.refresh(ass)
    db.close()

    # 4) Submit responses
    payload = [
        {"question_id": "1", "answer": "1"},
        {"question_id": "2", "answer": "5"},
    ]
    resp1 = client.post(
        f"/v1/assessments/{ass.id}/responses",
        headers=headers,
        json=payload,
    )

    assert resp1.status_code == status.HTTP_200_OK, resp1.text
    body1 = resp1.json()

    # Contract: backend returns resume/state pointer payload (not list)
    assert isinstance(body1, dict), body1
    assert body1.get("assessment_id") == ass.id
    assert body1.get("answered_count") == 2
    assert body1.get("last_answered_question_id") in ("2", 2)
    assert "next_question_id" in body1
    assert "is_complete" in body1

    # 5) Trigger result generation
    from app.routers.assessments import generate_result

    db = SessionLocal()
    generate_result(ass.id, db)
    db.close()

    # 6) Fetch the generated result
    resp2 = client.get(f"/v1/assessments/{ass.id}/result", headers=headers)
    assert resp2.status_code == status.HTTP_200_OK
    body2 = resp2.json()

    assert body2["assessment_id"] == ass.id
    assert "recommended_careers" in body2
    assert isinstance(body2["recommended_careers"], list)
    assert "recommended_stream" in body2
