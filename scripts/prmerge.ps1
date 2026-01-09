param(
  [string]$BaseBranch = "main"
)

# Fail fast
$ErrorActionPreference = "Stop"

# Helper: run a command and stop if it fails
function Invoke-Checked {
  param([string]$Cmd)
  Invoke-Expression $Cmd
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# Ensure we're in a git repo
Invoke-Checked "git rev-parse --is-inside-work-tree | Out-Null"

$current = (git branch --show-current).Trim()
if ($current -eq $BaseBranch) {
  Write-Host "Already on $BaseBranch. Run this from your PR branch." -ForegroundColor Yellow
  exit 1
}

# Run guardrail checks
Invoke-Checked "powershell -ExecutionPolicy Bypass -File `".\scripts\check.ps1`""

# Merge into base branch with a merge commit (keeps PR history visible)
Invoke-Checked "git switch $BaseBranch"

# If a remote exists, pull latest changes. Otherwise (local-only), skip.
$hasOrigin = (git remote | Where-Object { $_ -eq "origin" }).Count -gt 0
if ($hasOrigin) {
  Invoke-Checked "git pull"
} else {
  Write-Host "No remote 'origin' configured; skipping git pull (local-only workflow)." -ForegroundColor Yellow
}

Invoke-Checked "git merge --no-ff $current"

# Switch back to PR branch
Invoke-Checked "git switch $current"
