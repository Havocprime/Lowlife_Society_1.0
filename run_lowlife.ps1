param([switch]$NoInstall)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$log = Join-Path $here "lowlife_run.log"
Start-Transcript -Path $log -Append | Out-Null

function FinallyPause([string]$msg="Press Enter to close") {
  try { Stop-Transcript | Out-Null } catch {}
  Read-Host $msg | Out-Null
  exit
}

Write-Host "[LOWLIFE] Repo root: $PWD"

# .env bootstrap
if (-not (Test-Path .env) -and (Test-Path .env.example)) {
  Copy-Item .env.example .env -Force
  Write-Host "[LOWLIFE] Created .env from .env.example (fill DISCORD_TOKEN)."
}

# venv
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
  Write-Host "[LOWLIFE] Creating venv ..."
  try { & py -3.12 -m venv .venv } catch { & py -m venv .venv }
}

# activate
& .\.venv\Scripts\Activate.ps1

# deps
if (-not $NoInstall) {
  Write-Host "[LOWLIFE] Ensuring dependencies ..."
  python -m pip install -U pip
  python -m pip install discord.py==2.4.0 python-dotenv pydantic PyYAML
}

# purge caches
Write-Host "[LOWLIFE] Purging __pycache__ and *.pyc ..."
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Filter *.pyc | Remove-Item -Force -ErrorAction SilentlyContinue

# legacy scan
Write-Host "[LOWLIFE] Scanning for legacy 'DuelState' references ..."
$hits = Select-String -Path "GAME\src\**\*.py" -Pattern "DuelState" -List -ErrorAction SilentlyContinue
if ($hits) { $hits | ForEach-Object { Write-Host "  [WARN] $($_.Path)" } }

# run
$env:PYTHONPATH = (Get-Location).Path + "\GAME"
Write-Host "[LOWLIFE] PYTHONPATH=$($env:PYTHONPATH)"
Write-Host "[LOWLIFE] Starting bot ..."

try {
  python -m src.bot.bot
}
catch {
  Write-Host "[LOWLIFE] FATAL: $($_.Exception.Message)"
  Write-Host ($_ | Out-String)
  FinallyPause "Bot crashed. Check lowlife_run.log. Press Enter to close"
}

FinallyPause "Bot exited. Press Enter to close"
