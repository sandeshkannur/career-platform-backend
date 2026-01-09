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

    # Seed an assessment directly
    db = SessionLocal()
    ass = models.Assessment(user_id=1)
    db.add(ass)
    db.commit()
    db.refresh(ass)
    db.close()

    # Act: submit responses
    payload = [
        {"question_id": "Q1", "answer": "Answer A"},
        {"question_id": "Q2", "answer": "Answer B"},
    ]
    resp1 = client.post(
        f"/v1/assessments/{ass.id}/responses",
        headers=headers,
        json=payload,
    )
    assert resp1.status_code == status.HTTP_200_OK
    body1 = resp1.json()
    assert isinstance(body1, list)
    assert body1[0]["question_id"] == "Q1"
    assert body1[0]["answer"] == "Answer A"

    # Manually trigger the stubbed result generation
    from app.routers.assessments import generate_result
    db = SessionLocal()
    generate_result(ass.id, db)
    db.close()

    # Act: fetch the generated result
    resp2 = client.get(f"/v1/assessments/{ass.id}/result", headers=headers)
    assert resp2.status_code == status.HTTP_200_OK
    body2 = resp2.json()
    assert body2["assessment_id"] == ass.id
    assert isinstance(body2["recommended_careers"], list)
    assert "recommended_stream" in body2
