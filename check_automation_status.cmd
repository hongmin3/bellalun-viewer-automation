@echo off
setlocal
cd /d "%~dp0"
set "BLN_MAX_DAYS=%~1"
if "%BLN_MAX_DAYS%"=="" set "BLN_MAX_DAYS=7"
python tools_automation_status.py --max-age-days %BLN_MAX_DAYS% --notify
exit /b %ERRORLEVEL%
