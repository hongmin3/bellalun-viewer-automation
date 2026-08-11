@echo off
setlocal
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
  echo [FAIL] 관리자 권한으로 실행해야 합니다.
  exit /b 2
)
python run.py run-regression
set "BLN_EXIT=%ERRORLEVEL%"
echo.
echo 결과는 Reports 폴더에 HTML, CSV, JSON, TXT로 저장되었습니다.
exit /b %BLN_EXIT%
