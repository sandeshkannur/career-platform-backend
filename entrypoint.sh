#!/usr/bin/env sh
set -e

echo "⏳ Waiting for Postgres to be ready…"
# (we’re already in /app, wait_for_db.py lives at app/wait_for_db.py)
python app/wait_for_db.py \
  --host     "$POSTGRES_HOST" \
  --port     "$POSTGRES_PORT" \
  --user     "$POSTGRES_USER" \
  --password "$POSTGRES_PASSWORD" \
  --db       "$POSTGRES_DB"

echo "🚀 Applying database migrations…"
alembic upgrade head

echo "✅ Migrations applied. Starting Uvicorn…"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
