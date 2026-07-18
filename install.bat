@echo off
setlocal
chcp 65001 >nul
title Resume Detective - Source Setup

echo ============================================
echo   Resume Detective - Source Setup
echo ============================================
echo.
echo This script is for source-code users only.
echo If you want to use the packaged app, run ResumeDetective.exe instead.
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    echo Please install Python 3.11+ first, then run this script again.
    pause
    exit /b 1
)

python -m pip --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] pip is not available for this Python environment.
    echo Try reinstalling Python and enable pip.
    pause
    exit /b 1
)

echo [1/3] Installing Python packages...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip.
    pause
    exit /b 1
)

python -m pip install ^
    PyQt6 ^
    requests ^
    openpyxl ^
    PyMuPDF ^
    Pillow ^
    python-docx ^
    comtypes
if errorlevel 1 (
    echo [ERROR] Failed to install required packages.
    pause
    exit /b 1
)
echo [OK] Python packages installed.
echo.

echo [2/3] Checking optional Reasonix CLI...
set "CLI_DIR=%~dp0Reasonix Cli"
set "CLI_EXE=%CLI_DIR%\reasonix.exe"
if exist "%CLI_EXE%" (
    echo [OK] Reasonix CLI found:
    echo      %CLI_EXE%
) else (
    echo [INFO] Reasonix CLI not found.
    echo        AI API mode will still work.
    echo        To enable Reasonix CLI later, place reasonix.exe here:
    echo        %CLI_DIR%
)
echo.

echo [3/3] Preparing private data folders outside the repository...
python -c "import paths; paths.ensure_data_directories(); print('[OK] Private data:', paths.DATA_DIR)"
if errorlevel 1 (
    echo [ERROR] Failed to prepare the private data directory.
    pause
    exit /b 1
)
echo.

echo ============================================
echo Setup complete.
echo Start the source version with:
echo python main.py
echo ============================================
pause
exit /b 0
