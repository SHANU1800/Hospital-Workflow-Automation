@echo off
setlocal

echo ================================================
echo   Hospital Workflow Automation - Quick Start
echo ================================================
echo.

set "PROJECT_DIR=%~dp0hospital-agent-system"

if not exist "%PROJECT_DIR%\docker-compose.yml" (
    echo [ERROR] Could not find docker-compose.yml in:
    echo         %PROJECT_DIR%
    echo.
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%"

REM Prefer modern Docker Compose command, fallback to legacy docker-compose
docker compose version >nul 2>&1
if %errorlevel%==0 (
    set "COMPOSE_CMD=docker compose"
) else (
    docker-compose version >nul 2>&1
    if %errorlevel%==0 (
        set "COMPOSE_CMD=docker-compose"
    ) else (
        echo [ERROR] Docker Compose not found.
        echo         Please install Docker Desktop and try again.
        echo.
        pause
        exit /b 1
    )
)

echo [INFO] Starting services using %COMPOSE_CMD% ...
echo [INFO] App URL: http://localhost:8000
echo.
start "" "http://localhost:8000"
call %COMPOSE_CMD% up --build

endlocal
