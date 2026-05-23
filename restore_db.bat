@echo off
REM ASCII-only shim. Delegates to scripts\restore_db.ps1
REM Usage:  restore_db.bat              (auto-picks latest in backups\)
REM        restore_db.bat path\to.dump  (specific file)
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\restore_db.ps1" %*
set "PS_EXIT=%ERRORLEVEL%"
echo.
pause
endlocal & exit /b %PS_EXIT%
