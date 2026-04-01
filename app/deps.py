"""
FastAPI database dependency — single source of truth for get_db().
All routers must import get_db from here, never from app.database directly.
"""
from .database import SessionLocal
from sqlalchemy.orm import Session


def get_db():
    """
    Yields a SQLAlchemy DB session for use as a FastAPI dependency.
    Closes the session automatically after the request completes.

    Usage in a router:
        db: Session = Depends(get_db)
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
