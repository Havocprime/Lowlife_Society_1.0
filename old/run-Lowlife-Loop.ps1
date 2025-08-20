# run-Lowlife-Loop.ps1
# Same as run-Lowlife.ps1 but auto-restarts the bot if it crashes/exits

$ProjectPath = "C:\Users\Havocprime\Desktop\Lowlife_Society\lowlife_starter"

$ErrorActionPreference = "Stop"
Set-Location $ProjectPath
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

if (!(Test-Path ".\.venv\Scripts\python.exe")) {
  Write-Host "Creating virtual environment (.venv)..." -ForegroundColor Yellow
  py -3 -m venv .venv
}

. .\.venv\Scripts\Activate.ps1

Write-Host "Auto-restart loop running. Press Ctrl+C to stop." -ForegroundColor Green
while ($true) {
  try {
    python -m src.bot.bot
  } catch {
    Write-Host "Bot crashed: $($_.Exception.Message)" -ForegroundColor Red
  }
  Write-Host "Restarting in 2 seconds..." -ForegroundColor Yellow
  Start-Sleep -Seconds 2
}
