# backend/app/routers/key_skills.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List

from app import models, schemas, deps
from app.auth.auth import get_current_active_user

router = APIRouter(
    tags=["Key Skills"],
    dependencies=[Depends(get_current_active_user)],
)

@router.post("", response_model=schemas.KeySkill, status_code=status.HTTP_201_CREATED)
def create_key_skill(
    skill: schemas.KeySkillCreate,
    db: Session = Depends(deps.get_db),
):
    # Ensure the referenced cluster exists
    cluster = db.query(models.CareerCluster).get(skill.cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CareerCluster with provided cluster_id does not exist"
        )
    # Prevent duplicates
    if db.query(models.KeySkill).filter_by(name=skill.name).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="KeySkill already exists"
        )
    db_skill = models.KeySkill(name=skill.name, cluster_id=skill.cluster_id)
    db.add(db_skill)
    try:
        db.commit()
        db.refresh(db_skill)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create KeySkill due to integrity error"
        )
    return db_skill

@router.get("", response_model=List[schemas.KeySkill])
def list_key_skills(db: Session = Depends(deps.get_db)):
    return db.query(models.KeySkill).all()

@router.get("/{skill_id}", response_model=schemas.KeySkill)
def get_key_skill(
    skill_id: int,
    db: Session = Depends(deps.get_db)
):
    ks = db.query(models.KeySkill).get(skill_id)
    if not ks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KeySkill not found"
        )
    return ks

@router.put("/{skill_id}", response_model=schemas.KeySkill, dependencies=[Depends(get_current_active_user)])
def update_key_skill(
    skill_id: int,
    skill_data: schemas.KeySkillCreate,
    db: Session = Depends(deps.get_db),
):
    ks = db.query(models.KeySkill).get(skill_id)
    if not ks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KeySkill not found"
        )
    # Ensure the referenced cluster exists
    cluster = db.query(models.CareerCluster).get(skill_data.cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CareerCluster with provided cluster_id does not exist"
        )
    # Prevent name conflicts
    existing = (
        db.query(models.KeySkill)
        .filter(models.KeySkill.name == skill_data.name)
        .filter(models.KeySkill.id != skill_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Another KeySkill with this name already exists"
        )
    ks.name = skill_data.name
    ks.cluster_id = skill_data.cluster_id
    try:
        db.commit()
        db.refresh(ks)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update KeySkill due to integrity error"
        )
    return ks

@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(get_current_active_user)])
def delete_key_skill(
    skill_id: int,
    db: Session = Depends(deps.get_db),
):
    ks = db.query(models.KeySkill).get(skill_id)
    if not ks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KeySkill not found"
        )
    db.delete(ks)
    db.commit()
    return
