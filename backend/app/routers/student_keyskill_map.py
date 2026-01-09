# app/routers/student_keyskill_map.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app import models, schemas, deps
from app.auth.auth import get_current_active_user

router = APIRouter(
    prefix="/student-keyskill-map",
    tags=["StudentKeySkillMap"],
    dependencies=[Depends(get_current_active_user)],
)


@router.post("", response_model=schemas.StudentKeySkillMap)
def assign_keyskill_to_student(
    mapping: schemas.StudentKeySkillMapCreate,
    db: Session = Depends(deps.get_db),
):
    """
    Assign a KeySkill to a Student.
    """
    db_mapping = models.StudentKeySkillMap(**mapping.dict())
    db.add(db_mapping)
    db.commit()
    db.refresh(db_mapping)
    return db_mapping


@router.get("", response_model=List[schemas.StudentKeySkillMap])
def list_student_keyskill_mappings(
    db: Session = Depends(deps.get_db),
):
    """
    List all Student ↔ KeySkill mappings.
    """
    return db.query(models.StudentKeySkillMap).all()


@router.delete("/{mapping_id}")
def delete_student_keyskill_mapping(
    mapping_id: int,
    db: Session = Depends(deps.get_db),
):
    """
    Delete a Student ↔ KeySkill mapping by its ID.
    """
    mapping = (
        db.query(models.StudentKeySkillMap)
        .filter(models.StudentKeySkillMap.id == mapping_id)
        .first()
    )
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    db.delete(mapping)
    db.commit()
    return {"message": f"Mapping ID {mapping_id} has been deleted."}
