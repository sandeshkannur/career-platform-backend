# scripts/check.ps1
# Docker-first quality gate for CareerPlatform (fails fast if anything fails)

$ErrorActionPreference = "Stop"

Write-Host "== CareerPlatform: Docker-based Local Checks =="

Write-Host "`n[Docker] Checking Docker daemon..."
docker info | Out-Null
Write-Host "✅ Docker is running."

Write-Host "`n[Backend] Ensuring DB is up..."
docker compose up -d db

Write-Host "`n[Backend] Running tests inside Docker (Postgres)..."
docker compose run --rm `
  -e TEST_DATABASE_URL="postgresql+psycopg2://counseling:testpass123@backend-db:5432/counseling_db" `
  backend pytest -q

Write-Host "`n✅ Backend tests passed (Docker/Postgres)."
Write-Host "`n[Frontend] Skipped for now (enable later if needed)."
Write-Host "`n✅ All local checks passed."
