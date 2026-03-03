from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas, deps
from app.auth.auth import get_current_active_user

router = APIRouter(
    prefix="/students",
    tags=["Students"],
    dependencies=[Depends(get_current_active_user)],
)

@router.post("", response_model=schemas.Student)
def create_student(
    student: schemas.StudentCreate,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Creates a student profile for the currently authenticated user.
    - Idempotent: if profile already exists, return it.
    """

    # Check if student profile already exists for this user
    existing = (
        db.query(models.Student)
        .filter(models.Student.user_id == current_user.id)
        .first()
    )

    if existing:
        return existing

    # Create new student profile
    db_student = models.Student(
        **student.dict(),
        user_id=current_user.id
    )

    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    return db_student

@router.get("", response_model=List[schemas.Student])
def list_students(db: Session = Depends(deps.get_db)):
    return db.query(models.Student).all()
@router.get("/me", response_model=schemas.Student)
def get_my_student_profile(
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Returns the student profile for the currently authenticated user.
    This makes E2E tests idempotent (script can check /me before creating).
    """
    student = db.query(models.Student).filter(models.Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return student
@router.get("/me", response_model=schemas.Student)
def get_my_student_profile(
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    student = (
        db.query(models.Student)
        .filter(models.Student.user_id == current_user.id)
        .first()
    )

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    return student
@router.get("/{student_id}", response_model=schemas.Student)
def get_student(
    student_id: int,
    db: Session = Depends(deps.get_db),
):
    db_student = db.query(models.Student).get(student_id)
    if not db_student:
        raise HTTPException(status_code=404, detail="Student not found")
    return db_student

@router.put("/{student_id}", response_model=schemas.Student)
def update_student(
    student_id: int,
    student: schemas.StudentCreate,
    db: Session = Depends(deps.get_db),
):
    db_student = db.query(models.Student).get(student_id)
    if not db_student:
        raise HTTPException(status_code=404, detail="Student not found")
    for key, value in student.dict().items():
        setattr(db_student, key, value)
    db.commit()
    db.refresh(db_student)
    return db_student

@router.delete("/{student_id}")
def delete_student(
    student_id: int,
    db: Session = Depends(deps.get_db),
):
    db_student = db.query(models.Student).get(student_id)
    if not db_student:
        raise HTTPException(status_code=404, detail="Student not found")
    db.delete(db_student)
    db.commit()
    return {"message": f"Student with ID {student_id} has been deleted."}
