@echo off
setlocal
REM cd to this .cmd's folder
cd /d "%~dp0"

REM activate venv if present
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

REM live stdout/stderr + chattier logs
set PYTHONUNBUFFERED=1
set LOG_LEVEL=DEBUG

REM run from GAME so src.* imports resolve
pushd "GAME"
python -X faulthandler -m src.bot.bot
set EXITCODE=%ERRORLEVEL%
popd

echo.
echo =======================
echo Bot exited with code %EXITCODE%
echo =======================
pause
endlocal
