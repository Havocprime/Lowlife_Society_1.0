@echo off
setlocal ENABLEDELAYEDEXPANSION

:: ***** UTF-8 everywhere *****
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONLEGACYWINDOWSSTDIO=1

:: cd to this .cmd's folder
cd /d "%~dp0"

:: activate venv if present
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

:: live stdout/stderr + chattier logs
set PYTHONUNBUFFERED=1
set LOG_LEVEL=DEBUG

:: run from GAME so src.* imports resolve
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
