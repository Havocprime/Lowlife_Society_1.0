@echo off
setlocal
cd /d %~dp0
set TS=%DATE:~10,4%%DATE:~4,2%%DATE:~7,2%-%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%
set TS=%TS: =0%
if not exist backups mkdir backups
copy /Y data\lowlife.db backups\lowlife-%TS%.db >NUL
echo Wrote backups\lowlife-%TS%.db
