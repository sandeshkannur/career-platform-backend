# pr18_auth_and_projection_verify.ps1
# PR-18: Auth + projection checks for /v1/reports/scorecard/{student_id}
# - No header parsing (avoids ConvertFrom-Json "HTTP" bugs)
# - Auto-discovers student ids from DB
# - Auto-seeds assessment + assessment_results for "other student" so admin test is deterministic

$ErrorActionPreference = "Stop"

# ==== Configure ====
$BASE = $env:BASE
if (-not $BASE) { $BASE = "http://127.0.0.1:8000" }

# Known creds (from your message)
$ADMIN_EMAIL   = "aarav.sharma01@testmail.com"
$STUDENT_EMAIL = "aarav.student01@testmail.com"
$PASSWORD      = "Test@12345"

# DB settings
$DB_CONTAINER = "backend-db"
$DB_USER      = "counseling"
$DB_NAME      = "counseling_db"

# Defaults used only when seeding
$ASSESSMENT_VERSION     = "v1"
$SCORING_CONFIG_VERSION = "v1"

function Db-Scalar([string]$sql) {
  $out = & docker exec -i $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -P pager=off -t -A -c $sql 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "DB command failed (exit=$LASTEXITCODE). SQL: $sql`nOutput:`n$out"
  }
  if ($null -eq $out) { return "" }
  return ($out | Out-String).Trim()
}

function Db-ExecStdin([string]$sqlText) {
  $out = ($sqlText | & docker exec -i $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -P pager=off -t -A) 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "DB stdin failed (exit=$LASTEXITCODE). SQL:`n$sqlText`nOutput:`n$out"
  }
  return ($out | Out-String).Trim()
}

function Get-StudentIdByEmail([string]$email) {
  $q = "select s.id from students s join users u on u.id=s.user_id where u.email='$email' order by s.id limit 1;"
  $id = Db-Scalar $q
  if (-not $id) { throw "No student_id found for email=$email. Does this user have a student profile?" }
  return [int]$id
}

function Get-AnotherStudentId([int]$excludeId) {
  $q = "select id from students where id <> $excludeId order by id limit 1;"
  $id = Db-Scalar $q
  if (-not $id) { throw "No 'other' student_id found (need at least 2 students in DB)." }
  return [int]$id
}

function Get-UserIdForStudent([int]$studentId) {
  $q = "select user_id from students where id=$studentId;"
  $id = Db-Scalar $q
  if (-not $id) { throw "No user_id found for student_id=$studentId" }
  return [int]$id
}

function Get-Token([string]$email, [string]$password) {
  $tmp = Join-Path $env:TEMP ("login_" + [Guid]::NewGuid().ToString() + ".json")

  @{ email = $email; password = $password } |
    ConvertTo-Json -Compress |
    Out-File -Encoding utf8 $tmp

  $resp = curl.exe -s -X POST "$BASE/v1/auth/login" `
    -H "Content-Type: application/json" `
    --data-binary "@$tmp"

  Remove-Item $tmp -ErrorAction SilentlyContinue

  $obj = $resp | ConvertFrom-Json
  if (-not $obj.access_token) {
    throw "Login failed for $email. Response: $resp"
  }

  $token = ($obj.access_token.ToString()).Trim()
  $parts = $token.Split(".")
  if ($parts.Length -ne 3) {
    throw "Token is not a valid JWT (parts=$($parts.Length)). Raw token: [$token]"
  }
  return $token
}

function Http-Get([string]$url, [string]$token) {
  # Capture body + status code separately (no -i headers)
  $bodyFile = Join-Path $env:TEMP ("http_" + [Guid]::NewGuid().ToString() + ".txt")

  $code = curl.exe -s -o $bodyFile -w "%{http_code}" `
    -H "Authorization: Bearer $token" `
    $url

  $body = ""
  if (Test-Path $bodyFile) {
    $body = Get-Content -Raw $bodyFile
    Remove-Item $bodyFile -ErrorAction SilentlyContinue
  }

  return [pscustomobject]@{
    code = [int]$code
    body = $body
    url  = $url
  }
}

function Assert-ContainsNoNumericInternals([string]$jsonText) {
  # Student-safe payload should not expose numeric internals
  $forbidden = @('"career_scores"', '"cluster_scores"', '"keyskill_scores"', '"weight"', '"normalized"', '"score"')

  foreach ($f in $forbidden) {
    if ($jsonText -match [regex]::Escape($f)) {
      throw "Student-safe payload leaked forbidden field: $f"
    }
  }
}

function Ensure-StudentHasReportReady([int]$studentId) {
  $userId = Get-UserIdForStudent $studentId

  # 1) Ensure at least one assessment exists
  $count = [int](Db-Scalar "select count(*) from assessments where user_id=$userId;")
  if ($count -eq 0) {
    Write-Host "Seed: inserting assessment for student_id=$studentId (user_id=$userId)"
    Db-ExecStdin @"
insert into assessments (user_id, submitted_at, assessment_version, scoring_config_version)
values ($userId, now(), '$ASSESSMENT_VERSION', '$SCORING_CONFIG_VERSION');
"@ | Out-Null
  } else {
    Write-Host "Seed check: student_id=$studentId already has assessments (count=$count)"
  }

  # 2) Ensure latest assessment has assessment_results
  $latestAssessmentId = Db-Scalar "select id from assessments where user_id=$userId order by id desc limit 1;"
  if (-not $latestAssessmentId) { throw "Could not find latest assessment for user_id=$userId" }

  $resultCount = [int](Db-Scalar "select count(*) from assessment_results where assessment_id=$latestAssessmentId;")
  if ($resultCount -eq 0) {
    Write-Host "Seed: inserting assessment_results for assessment_id=$latestAssessmentId (student_id=$studentId)"
    Db-ExecStdin @"
insert into assessment_results (assessment_id, recommended_stream, recommended_careers, skill_tiers, generated_at)
values (
  $latestAssessmentId,
  null,
  '[{"career_name":"Engineer"}]'::jsonb,
  '{}'::jsonb,
  now()
)
on conflict (assessment_id) do update
set
  recommended_stream   = excluded.recommended_stream,
  recommended_careers  = excluded.recommended_careers,
  skill_tiers          = excluded.skill_tiers,
  generated_at         = excluded.generated_at;
"@ | Out-Null
  } else {
    Write-Host "Seed check: assessment_results already present for assessment_id=$latestAssessmentId"
  }
}

Write-Host "== PR18 Auth & Projection Verify =="

# Auto-discover student ids
$OWN_STUDENT_ID   = Get-StudentIdByEmail $STUDENT_EMAIL
$OTHER_STUDENT_ID = Get-AnotherStudentId $OWN_STUDENT_ID

Write-Host "Resolved OWN_STUDENT_ID=$OWN_STUDENT_ID, OTHER_STUDENT_ID=$OTHER_STUDENT_ID"

# Tokens
$adminToken   = Get-Token $ADMIN_EMAIL $PASSWORD
$studentToken = Get-Token $STUDENT_EMAIL $PASSWORD

Write-Host "Tokens acquired"
Write-Host "Admin token parts: $((($adminToken).Split('.')).Length)"
Write-Host "Student token parts: $((($studentToken).Split('.')).Length)"

# [0] Token sanity
Write-Host ""
Write-Host "[0] Token sanity -> /v1/auth/me should be 200 for both tokens"

$meStudent = Http-Get "$BASE/v1/auth/me" $studentToken
if ($meStudent.code -ne 200) {
  throw "Student token did not validate on /v1/auth/me (got $($meStudent.code)). Body: $($meStudent.body)"
}

$meAdmin = Http-Get "$BASE/v1/auth/me" $adminToken
if ($meAdmin.code -ne 200) {
  throw "Admin token did not validate on /v1/auth/me (got $($meAdmin.code)). Body: $($meAdmin.body)"
}

Write-Host "OK: /v1/auth/me for both tokens"

# [1] Student -> own scorecard
Write-Host ""
Write-Host "[1] Student -> own student_id ($OWN_STUDENT_ID) should be 200"

$studentOwnUrl = "{0}/v1/reports/scorecard/{1}?view=student&format=json&locale=en" -f $BASE, $OWN_STUDENT_ID
$studentOwn = Http-Get $studentOwnUrl $studentToken

if ($studentOwn.code -ne 200) {
  throw "Expected 200 for student own report, got $($studentOwn.code). Body: $($studentOwn.body)"
}

Assert-ContainsNoNumericInternals $studentOwn.body

# Validate view field (this is why we parse JSON)
$studentObj = $studentOwn.body | ConvertFrom-Json
if ($studentObj.report_payload.report_meta.view -ne "student") {
  throw "Projection bug: expected report_meta.view=student but got $($studentObj.report_payload.report_meta.view)"
}

Write-Host "OK: Student own report (200 + projection safe)"

# [2] Student -> other student
Write-Host ""
Write-Host "[2] Student -> other student_id ($OTHER_STUDENT_ID) should be 403"

$studentOtherUrl = "{0}/v1/reports/scorecard/{1}?view=student&format=json&locale=en" -f $BASE, $OTHER_STUDENT_ID
$studentOther = Http-Get $studentOtherUrl $studentToken

if ($studentOther.code -ne 403) {
  throw "Expected 403 for student accessing other student_id, got $($studentOther.code). Body: $($studentOther.body)"
}

Write-Host "OK: 403 enforced"

# [3] Admin -> other student
Write-Host ""
Write-Host "[3] Admin -> other student_id ($OTHER_STUDENT_ID) should be 200 (ensure report-ready)"

Ensure-StudentHasReportReady $OTHER_STUDENT_ID

$adminOtherUrl = "{0}/v1/reports/scorecard/{1}?view=admin&format=json&locale=en" -f $BASE, $OTHER_STUDENT_ID
$adminOther = Http-Get $adminOtherUrl $adminToken

if ($adminOther.code -ne 200) {
  throw "Expected 200 for admin viewing other student_id, got $($adminOther.code). Body: $($adminOther.body)"
}

Write-Host "OK: Admin access (200)"
Write-Host ""
Write-Host "OK: PR18 auth + projection checks passed."
