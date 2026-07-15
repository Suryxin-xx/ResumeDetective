@echo off
setlocal
title ResumeDetective Release Builder

echo [ResumeDetective] Preparing a clean release package...
powershell.exe -NoProfile -NoLogo -ExecutionPolicy Bypass -File "%~dp0build_exe.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo [ERROR] Release build failed. Exit code: %EXIT_CODE%
) else (
    echo [OK] Release package/build completed.
)

echo.
pause
exit /b %EXIT_CODE%
