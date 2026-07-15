@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if exist "%~dp0ResumeDetectiveGateway.exe" (
    "%~dp0ResumeDetectiveGateway.exe"
) else (
    python "%~dp0gateway_main.py"
)

if errorlevel 1 pause
endlocal
