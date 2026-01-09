# =========================================================
# CareerPlatform – Full Project Snapshot Generator (LOCK-SAFE)
# Writes everything via one StreamWriter (avoids file lock issues)
# =========================================================

$RootPath = "C:\Users\sande\CareerPlatform"
$OutputFile = Join-Path $RootPath "careerplatform_full_snapshot_v2.txt"

$ExcludeDirs = @("pgdata","pgdata_backup","node_modules","__pycache__",".git",".venv","venv")

$IncludeExtensions = @(
  ".py",".js",".ts",".tsx",
  ".json",".yml",".yaml",
  ".env",".ini",".sql",
  ".md",".txt",".ps1",
  ".html",".css"
)

function Is-ExcludedPath($Path) {
  foreach ($dir in $ExcludeDirs) {
    if ($Path -match "\\$dir(\\|$)") { return $true }
  }
  return $false
}

# If file exists, try to delete it first (best effort)
if (Test-Path $OutputFile) {
  try { Remove-Item $OutputFile -Force -ErrorAction Stop } catch {}
}

# Create ONE writer for the whole run
$writer = New-Object System.IO.StreamWriter($OutputFile, $false, [System.Text.Encoding]::UTF8)

try {
  $writer.WriteLine("=================================================")
  $writer.WriteLine("CareerPlatform – Full Project Snapshot")
  $writer.WriteLine("Root Path : $RootPath")
  $writer.WriteLine("Generated : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
  $writer.WriteLine("=================================================")
  $writer.WriteLine()
  
  $writer.WriteLine("###############################")
  $writer.WriteLine("# PROJECT FILE STRUCTURE")
  $writer.WriteLine("###############################")
  $writer.WriteLine()

  $structureFile = Join-Path $RootPath "careerplatform_structure_1.txt"
   if (Test-Path $structureFile) {
     Get-Content $structureFile | ForEach-Object {
        $writer.WriteLine($_)
        }
      } else {
    $writer.WriteLine("[ERROR] careerplatform_structure_1.txt not found")
      }

  $writer.WriteLine()

  # SECTION 1: Structure
  $writer.WriteLine("###############################")
  $writer.WriteLine("# PROJECT FILE STRUCTURE")
  $writer.WriteLine("###############################")
  $writer.WriteLine()

  Get-ChildItem -Path $RootPath -Recurse | Where-Object { -not (Is-ExcludedPath $_.FullName) } | ForEach-Object {
    $relativePath = $_.FullName.Replace($RootPath, "").TrimStart("\")
    $writer.WriteLine($relativePath)
  }

  # SECTION 2: File contents
  $writer.WriteLine()
  $writer.WriteLine("###############################")
  $writer.WriteLine("# FILE CONTENTS")
  $writer.WriteLine("###############################")
  $writer.WriteLine()

  Get-ChildItem -Path $RootPath -Recurse -File |
    Where-Object {
      ($IncludeExtensions -contains $_.Extension.ToLower()) -and
      -not (Is-ExcludedPath $_.FullName)
    } |
    ForEach-Object {

      $relativePath = $_.FullName.Replace($RootPath, "").TrimStart("\")

      $writer.WriteLine()
      $writer.WriteLine("-------------------------------------------------")
      $writer.WriteLine("FILE: $relativePath")
      $writer.WriteLine("-------------------------------------------------")

      try {
        # Read file as text; if it fails, note error
        $content = Get-Content $_.FullName -Raw -ErrorAction Stop
        $writer.WriteLine($content)
      }
      catch {
        $writer.WriteLine("[ERROR: Unable to read file]")
      }
    }

  $writer.WriteLine()
  $writer.WriteLine("=================================================")
  $writer.WriteLine("END OF SNAPSHOT")
  $writer.WriteLine("=================================================")
}
finally {
  $writer.Close()
}
