param(
  [Parameter(Mandatory=$true)] [string] $Token
)

$base = "http://127.0.0.1:8000"

Write-Host "PR39 Beta Gate: v1/en (AQ,FACET,CAREER,CLUSTER)" -ForegroundColor Cyan
$en = Invoke-RestMethod -Method Get `
  -Uri "$base/v1/admin/validate-explainability-keys?version=v1&locale=en&required_families=AQ,FACET,CAREER,CLUSTER" `
  -Headers @{ Authorization = "Bearer $Token" }

if ($en.status -ne "ok") {
  Write-Host "FAIL: en gate failed" -ForegroundColor Red
  $en | ConvertTo-Json -Depth 10
  exit 1
}
Write-Host "PASS: en gate OK" -ForegroundColor Green

Write-Host "PR39 Beta Gate: v1/kn (CAREER,CLUSTER)" -ForegroundColor Cyan
$kn = Invoke-RestMethod -Method Get `
  -Uri "$base/v1/admin/validate-explainability-keys?version=v1&locale=kn&required_families=CAREER,CLUSTER" `
  -Headers @{ Authorization = "Bearer $Token" }

if ($kn.status -ne "ok") {
  Write-Host "FAIL: kn gate failed" -ForegroundColor Red
  $kn | ConvertTo-Json -Depth 10
  exit 1
}
Write-Host "PASS: kn gate OK" -ForegroundColor Green

Write-Host "✅ PR39 Beta Gate PASSED" -ForegroundColor Green
