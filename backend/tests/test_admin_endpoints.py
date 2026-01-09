# tests/test_admin_endpoints.py

import io
import datetime
import pytest
from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal

# 1A: Happy-Path CSV Upload → /v1/admin/upload-career-clusters
def test_upload_career_clusters_happy_path(client, admin_token):
    # Arrange: two new clusters in bytes
    csv_data = (
        "name,description\n"
        "Engineering,All engineering careers\n"
        "Medicine,Medical professions\n"
    )
    content = csv_data.encode("utf-8")
    files = {
        "file": (
            "clusters.csv",
            io.BytesIO(content),
            "text/csv"
        )
    }
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Act
    resp = client.post("/v1/admin/upload-career-clusters", headers=headers, files=files)

    # Assert HTTP + payload
    assert resp.status_code == 200
    assert resp.json() == {"status": "success", "inserted": 2}

    # Assert DB state
    db: Session = SessionLocal()
    try:
        count = db.query(models.CareerCluster).count()
        assert count == 2

        names = {c.name for c in db.query(models.CareerCluster).all()}
        assert names == {"Engineering", "Medicine"}
    finally:
        db.close()


# 1B: Happy-Path CSV Upload → /v1/admin/upload-careers
def test_upload_careers_happy_path(client, admin_token):
    # Seed one cluster so CSV cluster_id 1 is valid
    db = SessionLocal()
    cluster = models.CareerCluster(name="SeedCluster", description="for careers")
    db.add(cluster)
    db.commit()
    db.refresh(cluster)
    db.close()

    # Arrange: two new careers in bytes
    csv_data = (
        "title,description,cluster_id\n"
        "Developer,Writes code,{}\n"
        "Nurse,Healthcare provider,{}\n"
    ).format(cluster.id, cluster.id)
    content = csv_data.encode("utf-8")
    files = {
        "file": (
            "careers.csv",
            io.BytesIO(content),
            "text/csv"
        )
    }
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Act
    resp = client.post("/v1/admin/upload-careers", headers=headers, files=files)

    # Assert
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "success"
    assert body.get("inserted") == 2

    db = SessionLocal()
    try:
        titles = {c.title for c in db.query(models.Career).all()}
        assert titles == {"Developer", "Nurse"}
    finally:
        db.close()


# 1C: Happy-Path CSV Upload → /v1/admin/upload-keyskills
def test_upload_keyskills_happy_path(client, admin_token):
    # Seed one cluster so CSV cluster_id 1 is valid
    db = SessionLocal()
    cluster = models.CareerCluster(name="KSCluster", description="for keyskills")
    db.add(cluster)
    db.commit()
    db.refresh(cluster)
    db.close()

    csv_data = (
        "name,cluster_id\n"
        "Creativity,{}\n"
        "Empathy,{}\n"
    ).format(cluster.id, cluster.id)
    content = csv_data.encode("utf-8")
    files = {
        "file": (
            "keyskills.csv",
            io.BytesIO(content),
            "text/csv"
        )
    }
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.post("/v1/admin/upload-keyskills", headers=headers, files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "success"
    assert body.get("inserted") == 2

    db = SessionLocal()
    try:
        names = {ks.name for ks in db.query(models.KeySkill).all()}
        assert names == {"Creativity", "Empathy"}
    finally:
        db.close()


# 1D: Happy-Path JSON → /v1/admin/student-skill-map
def test_student_skill_map_happy_path(client, admin_token):
    # seed one student and one skill
    db = SessionLocal()
    student = models.Student(name="Alice", grade=10)
    skill = models.Skill(name="Logic")
    db.add_all([student, skill])
    db.commit()
    db.refresh(student)
    db.refresh(skill)
    db.close()

    payload = [{"student_id": student.id, "skill_id": skill.id}]
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/v1/admin/student-skill-map", headers=headers, json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "success"
    assert body.get("inserted") == 1

    db = SessionLocal()
    try:
        mapping = db.query(models.StudentSkillMap).one()
        assert mapping.student_id == student.id
        assert mapping.skill_id == skill.id
    finally:
        db.close()


# 1E: Happy-Path JSON → /v1/admin/student-keyskill-map
def test_student_keyskill_map_happy_path(client, admin_token):
    # seed one student and one keyskill
    db = SessionLocal()
    student = models.Student(name="Bob", grade=11)
    keyskill = models.KeySkill(name="Research", cluster_id=None)
    db.add_all([student, keyskill])
    db.commit()
    db.refresh(student)
    db.refresh(keyskill)
    db.close()

    payload = [{"student_id": student.id, "keyskill_id": keyskill.id}]
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/v1/admin/student-keyskill-map", headers=headers, json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "success"
    assert body.get("inserted") == 1

    db = SessionLocal()
    try:
        mapping = db.query(models.StudentKeySkillMap).one()
        assert mapping.student_id == student.id
        assert mapping.keyskill_id == keyskill.id
    finally:
        db.close()


# 1F: Happy-Path GET → /v1/admin/list-users
def test_list_users_happy_path(client, admin_token):
    # seed two users
    db = SessionLocal()
    u1 = models.User(
        full_name="U1",
        email="u1@example.com",
        hashed_password="x",
        dob=datetime.date(2000, 1, 1),
    )
    u2 = models.User(
        full_name="U2",
        email="u2@example.com",
        hashed_password="x",
        dob=datetime.date(1999, 1, 1),
    )
    db.add_all([u1, u2])
    db.commit()
    db.close()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/v1/admin/list-users", headers=headers)
    assert resp.status_code == 200
    users = resp.json()
    emails = {u["email"] for u in users}
    assert {"u1@example.com", "u2@example.com"}.issubset(emails)


# 1G: Happy-Path POST → /v1/admin/change-role/{user_id}
def test_change_role_happy_path(client, admin_token):
    # seed one user with default role
    db = SessionLocal()
    user = models.User(
        full_name="R1",
        email="r1@example.com",
        hashed_password="x",
        dob=datetime.date(2000, 1, 1),
        role="student"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        f"/v1/admin/change-role/{user.id}",
        headers=headers,
        json={"role": "editor"}
    )
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        updated = db.query(models.User).get(user.id)
        assert updated.role == "editor"
    finally:
        db.close()


# 1H: Happy-Path POST → /v1/admin/assign-guardian/{user_id}
def test_assign_guardian_happy_path(client, admin_token):
    # seed a minor user
    db = SessionLocal()
    kid = models.User(
        full_name="Kid",
        email="kid@example.com",
        hashed_password="x",
        dob=datetime.date(2010, 1, 1),
        is_minor=True
    )
    db.add(kid)
    db.commit()
    db.refresh(kid)
    db.close()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        f"/v1/admin/assign-guardian/{kid.id}",
        headers=headers,
        json={"guardian_email": "parent@example.com"}
    )
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        updated = db.query(models.User).get(kid.id)
        assert updated.guardian_email == "parent@example.com"
    finally:
        db.close()
