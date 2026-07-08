@echo off
chcp 65001 >nul
title Resume Detective - 一键安装

echo ============================================
echo   简历侦探 Resume Detective - 安装脚本
echo ============================================
echo.

:: 1. 安装 Python 依赖
echo [1/3] 安装 Python 依赖...
pip install PyQt6 PyPDF2 python-docx requests openpyxl PyMuPDF 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] pip 安装失败，请确保已安装 Python 3.10+
    pause
    exit /b 1
)
echo [OK] 依赖安装完成
echo.

:: 2. 检查可选的 Reasonix CLI（已不再默认内置）
echo [2/3] 检查 Reasonix CLI（可选组件）...
set "CLI_DIR=%~dp0Reasonix Cli"
set "CLI_EXE=%CLI_DIR%\reasonix.exe"

if exist "%CLI_EXE%" (
    echo [OK] 已检测到 Reasonix CLI
) else (
    echo [提示] Reasonix CLI 未安装
    echo 如需 CLI 通道，请下载 reasonix-windows-amd64 并解压到：
    echo %~dp0Reasonix Cli\
    echo.
    echo 下载地址：https://github.com/reasonix-ai/reasonix/releases
)
echo.
echo.

:: 3. 创建 data 目录
echo [3/3] 初始化数据目录...
if not exist "%~dp0data\" mkdir "%~dp0data"
if not exist "%~dp0data\Resumes\" mkdir "%~dp0data\Resumes"
if not exist "%~dp0data\chat_history\" mkdir "%~dp0data\chat_history"
echo [OK] 数据目录就绪
echo.

echo ============================================
echo   安装完成！运行 python main.py 启动
echo ============================================
pause
