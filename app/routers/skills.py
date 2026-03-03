# backend/app/routers/skills.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List

from app import models, schemas, deps
from app.auth.auth import get_current_active_user

router = APIRouter(
    prefix="/skills",
    tags=["Skills"],
    dependencies=[Depends(get_current_active_user)],
)

# ➕ Create a new skill
@router.post("", response_model=schemas.Skill, status_code=status.HTTP_201_CREATED)
def create_skill(
    skill: schemas.SkillCreate,
    db: Session = Depends(deps.get_db),
):
    # Prevent duplicates
    if db.query(models.Skill).filter_by(name=skill.name).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Skill already exists",
        )
    db_skill = models.Skill(name=skill.name)
    db.add(db_skill)
    try:
        db.commit()
        db.refresh(db_skill)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create skill due to integrity error",
        )
    return db_skill

# 🔍 Get all skills with optional name filtering
@router.get("", response_model=List[schemas.Skill])
def list_skills(
    name: str | None = None,
    db: Session = Depends(deps.get_db),
):
    query = db.query(models.Skill)
    if name:
        query = query.filter(models.Skill.name.ilike(f"%{name}%"))
    return query.all()

# 🔍 Get a skill by ID
@router.get("/{skill_id}", response_model=schemas.Skill)
def get_skill(
    skill_id: int,
    db: Session = Depends(deps.get_db),
):
    skill = db.get(models.Skill, skill_id)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Skill not found",
        )
    return skill

# 🔄 Update a skill
@router.put("/{skill_id}", response_model=schemas.Skill)
def update_skill(
    skill_id: int,
    skill_data: schemas.SkillCreate,
    db: Session = Depends(deps.get_db),
):
    skill = db.get(models.Skill, skill_id)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Skill not found",
        )
    # Prevent duplicates
    existing = (
        db.query(models.Skill)
        .filter(models.Skill.name == skill_data.name)
        .filter(models.Skill.id != skill_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Another skill with this name already exists",
        )
    skill.name = skill_data.name
    try:
        db.commit()
        db.refresh(skill)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update skill due to integrity error",
        )
    return skill

# 🗑️ Delete a skill
@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(
    skill_id: int,
    db: Session = Depends(deps.get_db),
):
    skill = db.get(models.Skill, skill_id)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Skill not found",
        )
    db.delete(skill)
    db.commit()
    return
