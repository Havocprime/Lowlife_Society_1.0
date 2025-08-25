# run-simple.ps1
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
python -m src.bot.bot
Read-Host "Press Enter to close" | Out-Null
