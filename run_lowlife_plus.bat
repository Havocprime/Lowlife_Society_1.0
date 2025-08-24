@echo off
setlocal ENABLEDELAYEDEXPANSION
title LOWLIFE Launcher

cd /d "%~dp0"
echo [LOWLIFE] Repo root: %cd%

if not exist ".env" (
  echo [LOWLIFE] .env not found. Copying from .env.example ...
  if exist ".env.example" copy /y ".env.example" ".env" >nul
)

if not exist ".venv\Scripts\python.exe" (
  echo [LOWLIFE] Creating virtual environment ...
  py -3.12 -m venv .venv || py -m venv .venv
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo [LOWLIFE] ERROR: could not activate venv.
  pause
  exit /b 1
)

echo [LOWLIFE] Ensuring dependencies ...
python -m pip install -U pip
python -m pip install discord.py==2.4.0 python-dotenv pydantic PyYAML

echo [LOWLIFE] Purging __pycache__ and *.pyc ...
for /d /r %%D in (__pycache__) do (
  rd /s /q "%%D" 2>nul
)
del /s /q *.pyc 2>nul

echo [LOWLIFE] Scanning for legacy 'DuelState' references ...
set _HAS_DUELSTATE=0
for /f "delims=" %%F in ('cmd /c "echo." & (for /r GAME\src %%G in (*.py) do @findstr /m /c:"DuelState" "%%G")') do (
  set _HAS_DUELSTATE=1
  echo   [WARN] Legacy reference in: %%F
)
if "!_HAS_DUELSTATE!"=="1" (
  echo [LOWLIFE] WARNING: Found old 'DuelState' code above. Replace or remove before continuing.
)

set "PYTHONPATH=%cd%\GAME"
echo [LOWLIFE] PYTHONPATH=%PYTHONPATH%
echo [LOWLIFE] Starting bot ...
python -m src.bot.bot

echo.
echo [LOWLIFE] Bot exited. Press any key to close this window.
pause >nul
endlocal
