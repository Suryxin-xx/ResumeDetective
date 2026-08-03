@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
echo [ResumeDetective] Running safety checks, tests, and release build...
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\build_windows.ps1" -ArchiveExisting %*
if errorlevel 1 (
  echo.
  echo Build failed. Review the first error above.
  pause
  exit /b 1
)
echo.
echo Build completed. See the newest version folder under .\releases\.
pause
