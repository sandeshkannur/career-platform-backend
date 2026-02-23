from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas, deps
from app.auth.auth import get_current_active_user

# Initialize router
router = APIRouter(
                    prefix="/student-skill-map",
                    tags=["Student ↔ Skill Map"],
                    dependencies=[Depends(get_current_active_user)],
                    )


# ➕ Assign a skill to a student
@router.post("", response_model=schemas.StudentSkillMap)
def assign_skill_to_student(mapping: schemas.StudentSkillMapCreate, db: Session = Depends(deps.get_db)):
    existing = db.query(models.StudentSkillMap).filter(
        models.StudentSkillMap.student_id == mapping.student_id,
        models.StudentSkillMap.skill_id == mapping.skill_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Mapping already exists")

    db_mapping = models.StudentSkillMap(**mapping.dict())
    db.add(db_mapping)
    db.commit()
    db.refresh(db_mapping)
    return db_mapping

# 📋 Get all student-skill mappings
@router.get("", response_model=List[schemas.StudentSkillMap])
def get_all_mappings(db: Session = Depends(deps.get_db)):
    return db.query(models.StudentSkillMap).all()

# 🗑️ Delete a mapping by ID
@router.delete("/{mapping_id}")
def delete_mapping(mapping_id: int, db: Session = Depends(deps.get_db)):
    mapping = db.query(models.StudentSkillMap).filter(models.StudentSkillMap.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    db.delete(mapping)
    db.commit()
    return {"message": f"Mapping with ID {mapping_id} deleted successfully."}

# 🎯 Get all skills for a given student
@router.get("/students/{student_id}/skills", response_model=List[schemas.Skill])
def get_skills_for_student(student_id: int, db: Session = Depends(deps.get_db)):
    mappings = db.query(models.StudentSkillMap).filter(models.StudentSkillMap.student_id == student_id).all()
    if not mappings:
        raise HTTPException(status_code=404, detail="No skills found for this student")

    skill_ids = [m.skill_id for m in mappings]
    skills = db.query(models.Skill).filter(models.Skill.id.in_(skill_ids)).all()
    return skills

# 🎯 Get all students for a given skill
@router.get("/skills/{skill_id}/students", response_model=List[schemas.Student])
def get_students_for_skill(skill_id: int, db: Session = Depends(deps.get_db)):
    mappings = db.query(models.StudentSkillMap).filter(models.StudentSkillMap.skill_id == skill_id).all()
    if not mappings:
        raise HTTPException(status_code=404, detail="No students found for this skill")

    student_ids = [m.student_id for m in mappings]
    students = db.query(models.Student).filter(models.Student.id.in_(student_ids)).all()
    return students
