import os
import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# -----------------------------
# Resolve paths & load .env
# -----------------------------
# backend/                <- this file lives in backend/alembic/env.py
#   alembic/
#   app/
# .env                    <- lives at repo root
BACKEND_DIR = Path(__file__).resolve().parents[1]          # .../CareerCounselingAI/backend
REPO_ROOT   = BACKEND_DIR.parent                           # .../CareerCounselingAI

# Make "backend" importable so "from app..." works when running Alembic from backend/
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Load .env if present (no hard dependency on python-dotenv to keep this lightweight)
dotenv_path = REPO_ROOT / ".env"
if dotenv_path.exists():
    try:
        from dotenv import load_dotenv  # optional
        load_dotenv(dotenv_path)
    except Exception:
        # If python-dotenv isn't installed, we simply skip; env vars may already be set in the shell
        pass

# -----------------------------
# Alembic config & logging
# -----------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -----------------------------
# Database URL resolution
# Priority: HOST_DATABASE_URL (host override) -> DATABASE_URL -> alembic.ini
# -----------------------------
db_url = (
    os.getenv("HOST_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or config.get_main_option("sqlalchemy.url")
)

if not db_url:
    raise RuntimeError(
        "No database URL found. Set HOST_DATABASE_URL or DATABASE_URL, "
        "or ensure sqlalchemy.url is set in alembic.ini."
    )

# Inject into Alembic so all commands use it
config.set_main_option("sqlalchemy.url", db_url)

# Helpful debug line so you can confirm what Alembic is using
print(f"DB_URL_USED={db_url}")

# -----------------------------
# Import metadata for autogenerate
# -----------------------------
# Your SQLAlchemy Base lives in backend/app/database.py and models in backend/app/models/*
from app.database import Base  # type: ignore
# Import models to ensure they’re registered on Base.metadata (adjust if your models path differs)
try:
    from app import models  # noqa: F401  # type: ignore
except Exception:
    # If you don't have models yet, this is fine during early bootstrapping
    pass

target_metadata = Base.metadata

# -----------------------------
# Migration runners
# -----------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,         # helpful for autogenerate when column types change
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode'."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
