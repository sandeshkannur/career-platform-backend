# pr18_db_sanity_checks.ps1
# PR-18: DB sanity checks for "report readiness" + analytics snapshot

$ErrorActionPreference = "Stop"

$DB_CONTAINER = "backend-db"
$DB_USER      = "counseling"
$DB_NAME      = "counseling_db"

$STUDENT_EMAIL = "aarav.student01@testmail.com"
$SCORING_CONFIG_VERSION = "v1"

function Db-Scalar([string]$sql) {
  $out = & docker exec -i $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -P pager=off -t -A -c $sql 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "DB command failed (exit=$LASTEXITCODE). SQL: $sql`nOutput:`n$out"
  }
  if ($null -eq $out) { return "" }
  return ($out | Out-String).Trim()
}

Write-Host "== PR18 DB sanity checks =="
Write-Host "Student email  : $STUDENT_EMAIL"
Write-Host "Expected config: scoring_config_version=$SCORING_CONFIG_VERSION"
Write-Host ""

$studentId = Db-Scalar "select s.id from students s join users u on u.id=s.user_id where u.email='$STUDENT_EMAIL' order by s.id limit 1;"
if (-not $studentId) { throw "No student row found for email=$STUDENT_EMAIL" }

$userId = Db-Scalar "select user_id from students where id=$studentId;"
if (-not $userId) { throw "No user_id found for student_id=$studentId" }

Write-Host "Resolved ids   : student_id=$studentId, user_id=$userId"
Write-Host ""

$assessmentsCount = Db-Scalar "select count(*) from assessments where user_id=$userId;"
Write-Host "[1] assessments rows for user_id=$userId : $assessmentsCount"

$latestAssessmentId = Db-Scalar "select id from assessments where user_id=$userId order by id desc limit 1;"
Write-Host "[2] latest assessment_id : $latestAssessmentId"

if (-not $latestAssessmentId) {
  Write-Host "FAIL: no assessments exist. PR18 report will likely return 404 'No assessments'."
  exit 1
}

$resultsCount = Db-Scalar "select count(*) from assessment_results where assessment_id=$latestAssessmentId;"
Write-Host "[3] assessment_results rows for assessment_id=$latestAssessmentId : $resultsCount"

if ([int]$resultsCount -eq 0) {
  Write-Host "FAIL: report not ready (missing assessment_results for latest assessment)."
  exit 1
} else {
  Write-Host "PASS: assessment_results exists -> report-ready."
}

$summaryCount = Db-Scalar "select count(*) from student_analytics_summary where student_id=$studentId and scoring_config_version='$SCORING_CONFIG_VERSION';"
Write-Host ""
Write-Host "[4] student_analytics_summary rows for student_id=$studentId, scoring_config_version=$SCORING_CONFIG_VERSION : $summaryCount"

if ([int]$summaryCount -eq 0) {
  Write-Host "WARN: analytics snapshot missing (some report views may still work; depends on your implementation)."
} else {
  $latestComputedAt = Db-Scalar "select max(computed_at) from student_analytics_summary where student_id=$studentId and scoring_config_version='$SCORING_CONFIG_VERSION';"
  Write-Host "PASS: analytics snapshot present (latest computed_at=$latestComputedAt)"
}

Write-Host ""
Write-Host "OK: PR18 DB sanity checks completed."
