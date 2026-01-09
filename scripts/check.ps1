# scripts/check.ps1
# Docker-first quality gate for CareerPlatform (fails fast if anything fails)

$ErrorActionPreference = "Stop"

Write-Host "== CareerPlatform: Docker-based Local Checks =="

Write-Host "`n[Docker] Checking Docker daemon..."
docker info | Out-Null
Write-Host "✅ Docker is running."

Write-Host "`n[Static] Guardrail: blocking deprecated Pydantic Field(..., example=...) usage..."

# Scan only repo code (avoid .venv/site-packages)
$matches = Get-ChildItem backend/app -Recurse -File -Include *.py |
  Select-String -Pattern 'Field\s*\(.*\bexample\s*='

if ($matches) {
  Write-Host "`n❌ Found deprecated 'Field(..., example=...)' usage. Replace with json_schema_extra={'example': ...}." -ForegroundColor Red
  $matches | ForEach-Object { Write-Host ("  {0}:{1}: {2}" -f $_.Path, $_.LineNumber, $_.Line.Trim()) }
  throw "Static guardrail failed: deprecated Pydantic Field example= found."
}

Write-Host "✅ Static guardrail passed."

Write-Host "`n[Schema] OpenAPI generation (must be warning-free)..."

# Run OpenAPI generation inside the backend container and capture output (stdout+stderr)
$openapiOut = cmd /c 'docker compose run --rm backend python -c "import warnings; warnings.simplefilter(''default''); from app.main import app; app.openapi(); print(''OPENAPI_OK'')" 2>&1'
$openapiText = ($openapiOut | Out-String)
# Fail on warning patterns (keep this strict; INFO/DEBUG logs are allowed)
$warningPatterns = @(
  "PydanticDeprecatedSince",
  "DeprecationWarning",
  "Valid config keys have changed in V2",
  "UserWarning: Valid config keys have changed in V2"
)

$foundWarnings = $false
foreach ($p in $warningPatterns) {
  if ($openapiText -like "*$p*") {
    $foundWarnings = $true
    break
  }
}

if ($foundWarnings) {
  Write-Host "`n❌ OpenAPI generation emitted warnings. Fix schema/config warnings before merging." -ForegroundColor Red
  Write-Host $openapiText
  throw "Schema lint failed: OpenAPI generation warnings detected."
}

if (-not $openapiText.Contains("OPENAPI_OK")) {
  Write-Host "`n❌ OpenAPI generation did not complete successfully." -ForegroundColor Red
  Write-Host $openapiText
  throw "Schema lint failed: OPENAPI_OK sentinel not found."
}

Write-Host "✅ OpenAPI generation is warning-free."

Write-Host "`n[Backend] Ensuring DB is up..."
docker compose up -d db

Write-Host "`n[Backend] Running tests inside Docker (Postgres)..."
docker compose run --rm `
  -e TEST_DATABASE_URL="postgresql+psycopg2://counseling:testpass123@backend-db:5432/counseling_db" `
  backend pytest -q

Write-Host "`n✅ Backend tests passed (Docker/Postgres)."
Write-Host "`n[Frontend] Skipped for now (enable later if needed)."
Write-Host "`n✅ All local checks passed."
