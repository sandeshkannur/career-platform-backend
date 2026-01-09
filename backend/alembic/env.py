import os
import sys
from logging.config import fileConfig
from urllib.parse import urlparse, urlunparse

from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv

# ---------------------------------------------------
# Load environment variables from project .env (repo root)
# backend/alembic/env.py -> .. (backend) -> .. (repo root)
# ---------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# Ensure "backend" folder is importable so "from app..." works
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Import metadata for autogenerate
from app.database import Base  # noqa: E402
from app import models          # noqa: F401, E402  (ensure models are registered)

# Alembic Config
config = context.config

# ───── Resolve DB URL (host-first) ─────
# 1) Prefer an override specifically for host migrations (HOST_DATABASE_URL).
# 2) Fallback to DATABASE_URL (works in Docker).
db_url = os.getenv("HOST_DATABASE_URL") or os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError(
        "No database URL found. Set HOST_DATABASE_URL (host override) or DATABASE_URL in your environment/.env."
    )

# If user wants automatic host swap when 'db' is used outside Docker:
# Set PREFER_HOST_LOCAL=1 (default 1) to replace 'db' -> 'localhost:5433'
prefer_host_local = os.getenv("PREFER_HOST_LOCAL", "1") == "1"
try:
    u = urlparse(db_url)
    if u.hostname == "db" and prefer_host_local:
        # Build new netloc with same user/pass but localhost:5433
        userinfo = ""
        if u.username:
            userinfo += u.username
            if u.password:
                userinfo += f":{u.password}"
            userinfo += "@"
        port = 5433  # adjust if your compose maps to a different host port
        new_netloc = f"{userinfo}localhost:{port}"
        db_url = urlunparse((u.scheme, new_netloc, u.path, u.params, u.query, u.fragment))
except Exception:
    # non-fatal: keep original db_url
    pass

# Override alembic.ini's sqlalchemy.url with our resolved URL
config.set_main_option("sqlalchemy.url", db_url)
# ───────────────────────────────────────

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata for autogenerate
target_metadata = Base.metadata


def _common_config_kwargs():
    """
    Shared Alembic configuration kwargs.
    - compare_type: detect type changes on autogenerate
    - render_as_batch: on SQLite, allow batch mode migrations (handy in dev)
    """
    kwargs = {
        "target_metadata": target_metadata,
        "compare_type": True,
    }
    if db_url.startswith("sqlite"):
        kwargs["render_as_batch"] = True
    return kwargs


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode'."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_common_config_kwargs(),
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
            **_common_config_kwargs(),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
