@echo off
setlocal
set PYTHONPATH=%~dp0GAME

REM migrate
python -m src.db.migrate
if errorlevel 1 goto :eof

REM start bot
python -m src.bot.bot
