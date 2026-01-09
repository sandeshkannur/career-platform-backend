from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas, deps
from app.auth.auth import get_current_active_user


# Initialize router for user-related endpoints
router = APIRouter(
    prefix="/careers",
    tags=["Careers"],
    dependencies=[Depends(get_current_active_user)],
)

# POST /users - Create a new user
@router.post("/users", response_model=schemas.UserCreate)
def create_user(user: schemas.UserCreate, db: Session = Depends(deps.get_db)):
    # 🔍 Check if the user with the given email already exists
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # 📝 Create a new User object and save to DB
    db_user = models.User(name=user.name, email=user.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)  # Refresh to get the ID and other DB-managed fields
    return db_user

# 📄 GET /users - Retrieve all users
@router.get("/users")
def get_users(db: Session = Depends(deps.get_db)):
    # 🔁 Return all users from the database
    return db.query(models.User).all()


# ----------------------------
# B15: Bootstrap Frontend Session
# ----------------------------
@router.get("/me", response_model=schemas.SessionUserOut)
def get_my_session(
    db: Session = Depends(deps.get_db),
    current_user=Depends(get_current_active_user),
):
    """
    B15: Bootstrap frontend session (read-only)
    Returns user profile + role (and optional student_profile)
    """

    # Fetch latest user state from DB (deterministic, read-only)
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token user",
        )

    # Optional: fetch linked student profile (if any)
    student = (
        db.query(models.Student)
        .filter(models.Student.user_id == user.id)
        .first()
    )

    student_profile = None
    if student:
        student_profile = schemas.StudentProfileOut(
            student_id=student.id,
            name=student.name,
            grade=student.grade,
        )

    return schemas.SessionUserOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        is_minor=user.is_minor,
        guardian_email=getattr(user, "guardian_email", None),
        student_profile=student_profile,
        message="Session active",
    )
