@echo off
chcp 65001 >nul 2>&1
REM Shopmind Recommendation Service Quick Start Script (Windows)

echo ================================
echo   Shopmind Recommendation Service Startup
echo ================================
echo.

REM Check if uv is installed
where uv >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] uv is not installed, please install uv:
    echo    pip install uv
    exit /b 1
)

REM Check .env file
if not exist .env (
    echo [WARNING] .env file does not exist, copying from .env.example...
    if exist .env.example (
        copy .env.example .env >nul
        echo [OK] .env file created, please edit and configure necessary parameters
        echo    Especially OPENAI_API_KEY and NACOS_SERVER_ADDR
    ) else (
        echo [ERROR] .env.example file not found
    )
    exit /b 0
)

echo [INFO] Syncing dependencies...
uv sync
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to sync dependencies
    exit /b 1
)

echo [INFO] Starting service (development mode)...
echo.

REM Change to script directory to ensure correct working directory
cd /d "%~dp0"

REM Set PYTHONPATH to include project root
set PYTHONPATH=%CD%;%PYTHONPATH%

REM Use python -m uvicorn instead of direct uvicorn command
uv run python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8086

pause
