from app.database import Base, engine
from app.wait_for_db import wait_for_postgres
import os


def run_startup_tasks(database_url: str, skip_db_wait: str) -> None:
    """
    PR-CLEAN-04 Step 4:
    Centralized startup orchestration.

    Behavior is IDENTICAL to previous main.py logic:
    - Wait for Postgres (unless sqlite or SKIP_DB_WAIT=1)
    - Run Base.metadata.create_all() when allowed
    """

    # ------------------------------------------------------------
    # WAIT FOR DATABASE (POSTGRES) IF REQUIRED
    # ------------------------------------------------------------
    if not database_url.startswith("sqlite") and skip_db_wait != "1":
        wait_for_postgres(
            host=os.getenv("POSTGRES_HOST", "db"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "counseling"),
            password=os.getenv("POSTGRES_PASSWORD", "password"),
            db=os.getenv("POSTGRES_DB", "counseling_db"),
        )
    else:
        print("INFO: Skipping wait_for_postgres (using SQLite or SKIP_DB_WAIT=1)")

    # ------------------------------------------------------------
    # DEV TABLE CREATION (DEV ONLY)
    # ------------------------------------------------------------
    # PR-CLEAN-05:
    # - In production, schema must be controlled via Alembic migrations.
    # - We keep create_all() only for local/dev convenience.
    env = (os.getenv("ENV", "dev") or "dev").strip().lower()

    if env == "dev" and skip_db_wait != "1":
        print("INFO: ENV=dev → running Base.metadata.create_all()")
    # IMPORTANT: Alembic-only. Do not create tables at runtime.
    #   Base.metadata.create_all(bind=engine)
    else:
        print("INFO: Skipping Base.metadata.create_all() (ENV != dev or SKIP_DB_WAIT=1)")
        if env != "dev":
            print("INFO: Production mode detected — expecting Alembic migrations to be applied.")
