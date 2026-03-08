# app/auth/auth.py

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import exists, and_  # ✅ UPDATED: and_ needed for clean EXISTS clause

from .. import models, schemas, deps

router = APIRouter()  # ✅ No internal prefix

# -------------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-key")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
ALGORITHM = "HS256"

# Refresh-token settings (cookie-based)
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "14"))
REFRESH_COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "refresh_token")

# Cookie flags (DEV defaults; tighten for AWS/prod)
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"  # set 1 in prod (HTTPS)
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")   # "none" if cross-site over HTTPS

# -------------------------------------------------------------------
# BETA EMAIL ALLOWLIST (PR-PROD01)
# -------------------------------------------------------------------
def _parse_allowed_emails(raw: Optional[str]) -> set[str]:
    """
    Parses allowlist env var like:
    CP_BETA_ALLOWED_EMAILS="a@x.com, b@y.com"
    into a lowercase set.
    """
    if not raw:
        return set()
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_beta_email_allowed(email: str) -> bool:
    """
    If CP_BETA_ALLOWED_EMAILS is unset/empty => allow all (dev-friendly).
    If set => only allow listed emails for BOTH signup and login.
    """
    allowed = _parse_allowed_emails(os.getenv("CP_BETA_ALLOWED_EMAILS"))
    if not allowed:
        return True
    return (email or "").strip().lower() in allowed

# -------------------------------------------------------------------
# PASSWORD HASHING
# -------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# -------------------------------------------------------------------
# OAUTH2 SCHEME
# -------------------------------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


# -------------------------------------------------------------------
# AUTH HELPERS
# -------------------------------------------------------------------
def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates an access token (JWT).
    Note: We also use this function to create refresh tokens by passing a longer expires_delta
    and adding a token type claim.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """
    Stores refresh token in an HttpOnly cookie (recommended for web apps).
    Frontend cannot read it via JS, but it will be automatically sent with credentials: "include".
    """
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,          # ✅ True in prod (HTTPS)
        samesite=COOKIE_SAMESITE,      # ✅ "none" for cross-site (requires secure=True)
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clears the refresh cookie on logout."""
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/")


def _decode_token(token: str) -> dict:
    """Internal helper to decode JWT with consistent error handling."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


# -------------------------------------------------------------------
# DEPENDENCIES
# -------------------------------------------------------------------
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(deps.get_db),
) -> models.User:
    """
    Validates the incoming Bearer token:
    - Must be a valid JWT
    - Must contain sub=email
    - Must be an ACCESS token (payload["type"] == "access")
      This prevents refresh tokens from being used as access tokens.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # ✅ Ensure token is an ACCESS token (not refresh)
        token_type = payload.get("type")
        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )

        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception

    return user


def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    return current_user


def require_role(role: str):
    def role_checker(current_user: models.User = Depends(get_current_active_user)):
        current_role = (getattr(current_user, "role", None) or "").strip().lower()
        required_role = (role or "").strip().lower()

        if current_role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation forbidden",
            )
        return current_user

    return role_checker

def require_roles(*allowed_roles: str):
    """
    Dependency to restrict endpoint access by roles.

    Usage:
        Depends(require_roles("admin"))
        Depends(require_roles("admin", "counsellor"))
    """
    def role_checker(current_user: models.User = Depends(get_current_active_user)):
        current_role = (getattr(current_user, "role", None) or "").strip().lower()
        allowed = {r.strip().lower() for r in allowed_roles if r is not None}

        if current_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation forbidden",
            )
        return current_user

    return role_checker
# Convenience aliases (module-level, no indentation)
require_admin = require_role("admin")
require_admin_or_counsellor = require_roles("admin", "counsellor")

def get_current_active_admin(
    current_user: models.User = Depends(get_current_active_user),
) -> models.User:
    if getattr(current_user, "role", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


# -------------------------------------------------------------------
# ROUTES
# -------------------------------------------------------------------
@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=schemas.Message)
def signup(user_in: schemas.UserCreate, db: Session = Depends(deps.get_db)):
    # ✅ Normalize email once
    email_normalized = (user_in.email or "").strip().lower()

    # ✅ PR-PROD01: Beta allowlist gate
    if not is_beta_email_allowed(email_normalized):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Beta access restricted. This email is not allowlisted.",
        )

    if db.query(models.User).filter(models.User.email == email_normalized).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    hashed_password = get_password_hash(user_in.password)

    today = datetime.utcnow().date()
    age = (
        today.year
        - user_in.dob.year
        - ((today.month, today.day) < (user_in.dob.month, user_in.dob.day))
    )
    is_minor = age < 18

    if is_minor and not user_in.guardian_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Guardian email required for minors",
        )

    new_user = models.User(
        full_name=user_in.full_name,
        email=email_normalized,
        hashed_password=hashed_password,
        dob=user_in.dob,
        is_minor=is_minor,
        guardian_email=user_in.guardian_email,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return schemas.Message(message="User created successfully")


@router.post("/login-json", response_model=schemas.Token)
def login_json(
    user_in: schemas.UserLogin,
    response: Response,
    db: Session = Depends(deps.get_db),
):
    """
    Login:
    - Returns short-lived access token in JSON (existing behavior).
    - Sets refresh token as HttpOnly cookie (new).
    """
    # ✅ Normalize email once
    email_normalized = (user_in.email or "").strip().lower()

    # ✅ PR-PROD01: Beta allowlist gate
    if not is_beta_email_allowed(email_normalized):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Beta access restricted. This email is not allowlisted.",
        )

    user = authenticate_user(db, email_normalized, user_in.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ✅ Access token (short-lived)
    access_token = create_access_token(
        data={
            "sub": user.email,
            "role": getattr(user, "role", "student"),
            "type": "access",
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    # ✅ Refresh token (longer-lived) stored in HttpOnly cookie
    refresh_token = create_access_token(
        data={
            "sub": user.email,
            "type": "refresh",
        },
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    _set_refresh_cookie(response, refresh_token)

    return schemas.Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )
@router.post("/login", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    response: Response = Response(),
    db: Session = Depends(deps.get_db),
):
    """
    OAuth2-compatible login (form encoded):
    - Accepts username/password in x-www-form-urlencoded (username is email in our system)
    - Returns short-lived access token in JSON
    - Sets refresh token as HttpOnly cookie
    """
    email = (form_data.username or "").strip().lower()
    password = form_data.password

    # ✅ PR-PROD01: Beta allowlist gate
    if not is_beta_email_allowed(email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Beta access restricted. This email is not allowlisted.",
        )

    user = authenticate_user(db, email, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={
            "sub": user.email,
            "role": getattr(user, "role", "student"),
            "type": "access",
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    refresh_token = create_access_token(
        data={
            "sub": user.email,
            "type": "refresh",
        },
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    _set_refresh_cookie(response, refresh_token)

    

    return schemas.Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.post("/refresh", response_model=schemas.Token)
def refresh_token(
    request: Request,
    response: Response,
    db: Session = Depends(deps.get_db),
):
    """
    Refresh:
    - Reads refresh token from HttpOnly cookie
    - Validates it
    - Returns a new access token
    - (Optionally could rotate refresh token later)
    """
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )

    payload = _decode_token(token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    email = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # ✅ Look up user so role/is_minor flags remain accurate
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    new_access_token = create_access_token(
        data={
            "sub": user.email,
            "role": getattr(user, "role", "student"),
            "type": "access",
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return schemas.Token(
        access_token=new_access_token,
        refresh_token=token,
        token_type="bearer"
    )


@router.post("/logout", response_model=schemas.Message)
def logout(response: Response):
    """
    Logout:
    - Clears refresh cookie.
    Frontend should also clear access token from sessionStorage (already implemented).
    """
    _clear_refresh_cookie(response)
    return schemas.Message(message="Logged out successfully")


# -------------------------------------------------------------------
# B15: Bootstrap Frontend Session (GET /v1/auth/me)
# -------------------------------------------------------------------
@router.get("/me", response_model=schemas.SessionUserOut)
def get_my_session(
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Returns the current logged-in user session payload for frontend bootstrap.
    Read-only, JWT-protected, idempotent.

    IMPORTANT:
    - consent_verified MUST be derived from consent_logs (compliance artifact),
      not stored on the user table.
    """

    # current_user already comes from DB via get_current_user() -> safe to use directly
    user = current_user

    # Optional: include linked student profile (if exists)
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

    # ✅ Derive consent_verified from consent_logs (student_user_id + verified_at)
    consent_verified = db.query(
        exists().where(
            and_(
                models.ConsentLog.student_user_id == user.id,
                models.ConsentLog.verified_at.isnot(None),
            )
        )
    ).scalar()

    return schemas.SessionUserOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=getattr(user, "role", "student"),  # safe default if role is missing
        is_minor=user.is_minor,
        guardian_email=getattr(user, "guardian_email", None),
        student_profile=student_profile,
        consent_verified=bool(consent_verified),  # ✅ critical for frontend routing
        message="Session active",
    )
