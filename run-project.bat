@echo off
setlocal EnableDelayedExpansion

echo.
echo ╔═══════════════════════════════════════════════════╗
echo ║   Hospital Workflow Automation  —  Plan 1.0       ║
echo ╚═══════════════════════════════════════════════════╝
echo.

set "PROJECT_DIR=%~dp0hospital-agent-system"

REM ── Check project directory ────────────────────────────
if not exist "%PROJECT_DIR%\docker-compose.yml" (
    echo [ERROR] docker-compose.yml not found in:
    echo         %PROJECT_DIR%
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%"

REM ── Detect Docker Compose command ─────────────────────
docker compose version >nul 2>&1
if %errorlevel%==0 (
    set "COMPOSE_CMD=docker compose"
) else (
    docker-compose version >nul 2>&1
    if %errorlevel%==0 (
        set "COMPOSE_CMD=docker-compose"
    ) else (
        echo [ERROR] Docker Compose not found. Install Docker Desktop.
        pause
        exit /b 1
    )
)

REM ── Check Docker is running ───────────────────────────
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not running. Please start Docker Desktop first.
    pause
    exit /b 1
)

REM ── Stop any leftover containers cleanly ─────────────
echo [INFO] Stopping any existing containers...
%COMPOSE_CMD% down --remove-orphans 2>nul

REM ── Build and start ───────────────────────────────────
echo [INFO] Building and starting services...
echo [INFO] This may take 1-2 minutes on first run (downloading images).
echo.

REM Start in detached mode so we can tail logs properly
%COMPOSE_CMD% up --build -d

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] docker compose up failed. Showing logs:
    %COMPOSE_CMD% logs
    pause
    exit /b 1
)

REM ── Wait for the app to be healthy ───────────────────
echo [INFO] Waiting for application to start...
set /a TRIES=0

:WAIT_LOOP
set /a TRIES+=1
if %TRIES% gtr 30 (
    echo.
    echo [WARN] Application taking longer than expected. Showing logs:
    %COMPOSE_CMD% logs --tail=50
    echo.
    echo [INFO] App may still be starting. Check http://localhost:8000
    goto :OPEN
)

REM Check if app container is healthy/running
%COMPOSE_CMD% ps --format json 2>nul | findstr /i "hospital_app" >nul 2>&1

REM Simple HTTP check using PowerShell
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8000/health' -TimeoutSec 2 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Application is healthy!
    goto :OPEN
)

timeout /t 2 /nobreak >nul
echo [INFO] Still waiting... (%TRIES%/30)
goto :WAIT_LOOP

:OPEN
echo.
echo ╔═══════════════════════════════════════════════════╗
echo ║  App running at:  http://localhost:8000           ║
echo ║  API docs at:     http://localhost:8000/docs      ║
echo ║  DB port:         localhost:5433                  ║
echo ╚═══════════════════════════════════════════════════╝
echo.

REM Open browser
start "" "http://localhost:8000"
timeout /t 2 /nobreak >nul
start "" "http://localhost:8000/docs"

REM Tail live logs so user can see activity
echo [INFO] Showing live logs (Ctrl+C to stop log view - containers keep running):
echo.
%COMPOSE_CMD% logs --follow --tail=30

endlocal
