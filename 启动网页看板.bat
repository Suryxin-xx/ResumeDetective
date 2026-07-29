@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if exist "%~dp0ResumeDetective.exe" goto packaged_gateway

where pythonw.exe >nul 2>nul
if errorlevel 1 goto python_missing

start "" pythonw.exe "%~dp0gateway_main.py" --silent
if errorlevel 1 goto launch_failed
exit /b 0

:packaged_gateway
start "" "%~dp0ResumeDetective.exe" --gateway --silent
if errorlevel 1 goto launch_failed
exit /b 0

:python_missing
echo Python GUI launcher was not found. Run install.bat first.
pause
exit /b 1

:launch_failed
echo Resume Detective Gateway could not be started.
pause
exit /b 1
