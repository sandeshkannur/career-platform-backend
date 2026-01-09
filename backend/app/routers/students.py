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

    Notes:
    - Request contract stays the same (name, grade only).
    - We set students.user_id = current_user.id server-side to enforce ownership.
    """

    db_student = models.Student(**student.dict(), user_id=current_user.id)

    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    return db_student

@router.get("", response_model=List[schemas.Student])
def list_students(db: Session = Depends(deps.get_db)):
    return db.query(models.Student).all()

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
