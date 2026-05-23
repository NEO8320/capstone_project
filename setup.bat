@echo off
REM ============================================================
REM  News Curator - setup shim (ASCII-only).
REM  Delegates to scripts\setup.ps1 which carries all Korean text.
REM  Required because cmd.exe parsing of UTF-8 .bat files is
REM  unreliable on Korean Windows (cp949 default code page).
REM ============================================================
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\setup.ps1"
set "PS_EXIT=%ERRORLEVEL%"
echo.
pause
endlocal & exit /b %PS_EXIT%
