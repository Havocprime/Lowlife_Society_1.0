$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $repo
$env:PYTHONPATH = $repo
python "$repo\scripts\db_maintenance.py"
