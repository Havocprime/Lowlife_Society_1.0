$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if (-not (Test-Path ".\.venv")) { python -m venv .venv }

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
if (Test-Path ".\requirements.txt") {
  & ".\.venv\Scripts\python.exe" -m pip install -r ".\requirements.txt"
} else {
  & ".\.venv\Scripts\python.exe" -m pip install discord.py python-dotenv pydantic PyYAML aiohttp
}

$env:PYTHONPATH = $here
& ".\.venv\Scripts\python.exe" ".\GAME\src\bot\bot.py"

if ($LASTEXITCODE -ne 0) { Write-Host "`nBot exited with code $LASTEXITCODE" -ForegroundColor Red }
Read-Host "Press Enter to close"
