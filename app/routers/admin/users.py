"""
Admin users router.
Exposes 5 endpoints under /v1/admin/:
  POST /student-skill-map       — bulk assign skills to students
  POST /student-keyskill-map    — bulk assign key skills to students
  GET  /list-users              — list all platform users
  POST /change-role/{user_id}   — change a user's role
  POST /assign-guardian/{user_id} — assign guardian email to a user

Role gate: admin only (inherited from router dependency).
Reads/writes: students, skills, keyskills, student_skill_map,
              student_keyskill_map, users tables.
"""
from typing import List, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import (
    Student,
    Skill,
    KeySkill,
    StudentSkillMap,
    StudentKeySkillMap,
    User as UserModel,
)
from app.schemas import (
    User as UserSchema,
    RoleChange,
    GuardianAssign,
)
from app.auth.auth import require_role, get_current_active_user

router = APIRouter(
    tags=["Admin Panel"],
    dependencies=[Depends(require_role("admin"))],
)


# ============================================================
# Student ↔ Skill / KeySkill mapping
# ============================================================

@router.post(
    "/student-skill-map",
    summary="Bulk map Student ↔ Skill",
)
def student_skill_map(
    mappings: List[Dict[str, int]],
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    inserted = 0
    for item in mappings:
        sid = item.get("student_id")
        kid = item.get("skill_id")
        if not db.query(Student).get(sid) or not db.query(Skill).get(kid):
            raise HTTPException(status_code=400, detail="Invalid student_id or skill_id")
        db.add(StudentSkillMap(student_id=sid, skill_id=kid))
        inserted += 1
    db.commit()
    return {"status": "success", "inserted": inserted}


@router.post(
    "/student-keyskill-map",
    summary="Bulk map Student ↔ KeySkill",
)
def student_keyskill_map(
    mappings: List[Dict[str, int]],
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    inserted = 0
    for item in mappings:
        sid = item.get("student_id")
        kkid = item.get("keyskill_id")
        if not db.query(Student).get(sid) or not db.query(KeySkill).get(kkid):
            raise HTTPException(status_code=400, detail="Invalid student_id or keyskill_id")
        db.add(StudentKeySkillMap(student_id=sid, keyskill_id=kkid))
        inserted += 1
    db.commit()
    return {"status": "success", "inserted": inserted}


# ============================================================
# User management
# ============================================================

@router.get(
    "/list-users",
    response_model=List[UserSchema],
    summary="List all users",
)
def list_users(
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    return db.query(UserModel).all()


@router.post(
    "/change-role/{user_id}",
    response_model=UserSchema,
    summary="Change a user's role",
)
def change_role(
    user_id: int,
    payload: RoleChange,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    user = db.query(UserModel).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = payload.role
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/assign-guardian/{user_id}",
    response_model=UserSchema,
    summary="Assign guardian to a user",
)
def assign_guardian(
    user_id: int,
    payload: GuardianAssign,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    user = db.query(UserModel).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.guardian_email = payload.guardian_email
    db.commit()
    db.refresh(user)
    return user
