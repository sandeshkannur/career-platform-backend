from .database import SessionLocal

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# 👇 convenience import so other routers can do:
#   from app.deps import get_current_user
#from app.auth.auth import get_current_user  # noqa