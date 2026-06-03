$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$pythonCandidates = @(
  "python",
  "py",
  "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)

$python = $null
foreach ($candidate in $pythonCandidates) {
  try {
    & $candidate -c "import sys, tkinter, PIL" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
      $python = $candidate
      break
    }
  } catch {
    continue
  }
}

if (-not $python) {
  throw "No usable Python with tkinter and Pillow was found."
}

if (Test-Path -LiteralPath ".\desktop_app_v0_2.py") {
  & $python desktop_app_v0_2.py
} else {
  & $python desktop_app.py
}
