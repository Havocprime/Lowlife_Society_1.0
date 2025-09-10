param(
[string]$Py="python",
[string]$VenvDir=".venv"
)


Write-Host "[bootstrap] creating venv..."
$null = & $Py -m venv $VenvDir


Write-Host "[bootstrap] activating..."
$activate = Join-Path $VenvDir "Scripts\Activate.ps1"
. $activate


Write-Host "[bootstrap] pip install -r requirements.txt"
pip install -r requirements.txt


Write-Host "[bootstrap] ensuring DB schema..."
& $Py GAME\src\db\verify_db.py


Write-Host "[bootstrap] done."