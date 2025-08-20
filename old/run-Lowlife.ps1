# run-Lowlife.ps1
# Launch the Lowlife bot from the project root so "src" is the top-level package.
# Usage:
#   .\run-Lowlife.ps1                # watch for file changes; restart on change
#   .\run-Lowlife.ps1 -Watch:$false  # run once, no watcher
#   .\run-Lowlife.ps1 -RestartOnCrash  # also auto-restart after crashes

param(
    [switch]$Watch = $true,
    [switch]$RestartOnCrash = $false
)

$ErrorActionPreference = "Stop"

# --- Resolve paths ---
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SrcPath     = Join-Path $ProjectRoot 'src'

# --- Ensure we're at the project root ---
Set-Location $ProjectRoot

# --- Helpers ---
function Clear-PyCache {
    try {
        Get-ChildItem -Recurse -Force -Directory -Filter '__pycache__' $SrcPath `
            | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    } catch { }
}

function Start-Bot {
    Write-Host "Starting Lowlife bot..." -ForegroundColor Cyan
    Write-Host "(cwd: $ProjectRoot)" -ForegroundColor DarkGray
    # IMPORTANT: run as a package so imports like 'src.core.*' work.
    python -m src.bot.bot
}

# Optional: simple file watcher for quick reload-on-save
$watcher = $null
if ($Watch) {
    $watcher = New-Object System.IO.FileSystemWatcher $SrcPath, '*.py'
    $watcher.IncludeSubdirectories = $true
    $watcher.EnableRaisingEvents = $true
    Register-ObjectEvent $watcher Changed -SourceIdentifier 'SrcChanged' | Out-Null
    Register-ObjectEvent $watcher Created -SourceIdentifier 'SrcChanged' | Out-Null
    Register-ObjectEvent $watcher Renamed -SourceIdentifier 'SrcChanged' | Out-Null
    Register-ObjectEvent $watcher Deleted -SourceIdentifier 'SrcChanged' | Out-Null
    Write-Host "Watch mode ON — will restart on .py changes. (Ctrl+C to stop)" -ForegroundColor Green
}

try {
    while ($true) {
        Clear-PyCache
        Start-Bot
        $exit = $LASTEXITCODE

        if ($RestartOnCrash -and $exit -ne 0) {
            Write-Host "Bot exited with code $exit. Restarting in 2 seconds..." -ForegroundColor Yellow
            Start-Sleep -Seconds 2
            continue
        }

        if ($Watch) {
            Write-Host "Bot stopped. Watching for changes... (Ctrl+C to stop)" -ForegroundColor Yellow
            # Wait for at least one file event before restarting
            Wait-Event -SourceIdentifier 'SrcChanged' | Out-Null
            # Drain any queued events to avoid rapid double restarts
            Get-Event -SourceIdentifier 'SrcChanged' | Remove-Event | Out-Null
            Write-Host "Change detected. Restarting..." -ForegroundColor Magenta
            continue
        }

        break  # no watch, no crash-restart → exit loop
    }
}
finally {
    if ($watcher) {
        Unregister-Event -SourceIdentifier 'SrcChanged' -ErrorAction SilentlyContinue
        $watcher.EnableRaisingEvents = $false
        $watcher.Dispose()
    }
    Write-Host "run-Lowlife.ps1 finished." -ForegroundColor DarkGray
}
