@echo off
REM ASCII-only shim. Delegates to scripts\backup_db.ps1
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\backup_db.ps1"
set "PS_EXIT=%ERRORLEVEL%"
echo.
pause
endlocal & exit /b %PS_EXIT%
