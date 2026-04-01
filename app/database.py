# app/database.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session


# ============================================================
# DATABASE URL RESOLUTION
# ============================================================

def _resolve_database_url() -> str:
    """
    Resolve DATABASE_URL using the following priority:
    1) DATABASE_URL (fully formed) from environment
    2) Construct from POSTGRES_* pieces (Docker defaults)

    Note: main.py already loads .env, so we avoid load_dotenv() here
    to keep this module import-side-effect-free.
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    # Docker-friendly defaults
    user = os.getenv("POSTGRES_USER", "counseling")
    password = os.getenv("POSTGRES_PASSWORD", "password")
    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "counseling_db")

    # Use psycopg2 driver explicitly (matches your logs/usage)
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


DATABASE_URL = _resolve_database_url()


# ============================================================
# SQLALCHEMY ENGINE / SESSION / BASE
# ============================================================

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


