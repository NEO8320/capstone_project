@echo off
REM ============================================================
REM  News Curator - diagnose shim (ASCII-only).
REM  Runs scripts\diagnose.ps1 which checks every layer:
REM    Docker, PostgreSQL, Backend, Frontend, Ollama, .env, DB rows.
REM ============================================================
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\diagnose.ps1"
set "PS_EXIT=%ERRORLEVEL%"
echo.
pause
endlocal & exit /b %PS_EXIT%
