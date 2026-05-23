@echo off
REM ============================================================
REM  News Curator - run_all shim (ASCII-only).
REM  Delegates to scripts\run_all.ps1 which spawns backend +
REM  frontend cmd windows. See README section 17-9.
REM ============================================================
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\run_all.ps1"
set "PS_EXIT=%ERRORLEVEL%"
echo.
pause
endlocal & exit /b %PS_EXIT%
