@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT_DIR=%~dp0"
set "PROJECT_DIR=%ROOT_DIR%hospital-agent-system"
set "APP_URL=http://localhost:8000"
set "HEALTH_URL=%APP_URL%/health"
set "DOCS_URL=%APP_URL%/docs"
set "MAX_TRIES=45"
set "WAIT_SECONDS=2"
set "ENV_FILE=%PROJECT_DIR%\.env"

echo.
echo ==================================================
echo   Hospital Workflow Automation - Launcher
echo ==================================================
echo.

if not exist "%PROJECT_DIR%\docker-compose.yml" (
    echo [ERROR] Could not find docker-compose.yml at:
    echo         "%PROJECT_DIR%"
    pause
    exit /b 1
)

if not exist "%ENV_FILE%" (
    echo [ERROR] Missing .env file:
    echo         "%ENV_FILE%"
    echo [HINT]  Create hospital-agent-system\.env with Neon DATABASE_URL values.
    pause
    exit /b 1
)

set "DATABASE_URL_VALUE="
for /f "tokens=1,* delims==" %%A in ('findstr /B /I "DATABASE_URL=" "%ENV_FILE%"') do (
    set "DATABASE_URL_VALUE=%%B"
)

if not defined DATABASE_URL_VALUE (
    echo [ERROR] DATABASE_URL is missing in "%ENV_FILE%".
    pause
    exit /b 1
)

echo !DATABASE_URL_VALUE! | findstr /I "db:5432 localhost:5433 hospital_db" >nul
if not errorlevel 1 (
    echo [ERROR] DATABASE_URL still points to old local docker database host.
    echo [HINT]  Update DATABASE_URL in .env to Neon/external Postgres before launch.
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%"

docker version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker CLI is not available.
    echo         Install Docker Desktop and make sure "docker" is in PATH.
    pause
    exit /b 1
)

docker compose version >nul 2>&1
if not errorlevel 1 (
    set "COMPOSE_CMD=docker compose"
) else (
    docker-compose version >nul 2>&1
    if not errorlevel 1 (
        set "COMPOSE_CMD=docker-compose"
    ) else (
        echo [ERROR] Docker Compose is not available.
        echo         Install/enable Docker Compose and try again.
        pause
        exit /b 1
    )
)

docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker engine is not running.
    echo         Start Docker Desktop and retry.
    pause
    exit /b 1
)

echo [INFO] Using compose command: !COMPOSE_CMD!
echo [INFO] Project directory: "%PROJECT_DIR%"
echo.

echo [INFO] Cleaning up previous containers (if any)...
!COMPOSE_CMD! down --remove-orphans >nul 2>&1

echo [INFO] Building and starting services in detached mode...
!COMPOSE_CMD! up --build -d
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start services. Recent logs:
    !COMPOSE_CMD! logs --tail=100
    echo.
    echo [HINT] If build failed while pulling python:3.11-slim with TLS/HTTPS errors:
    echo [HINT] - Open Docker Desktop ^> Settings ^> Resources ^> Proxies and verify/disable proxy settings
    echo [HINT] - Retry image pull: docker pull python:3.11-slim
    echo [HINT] - Check VPN/corporate proxy/firewall that may intercept Docker Hub HTTPS traffic
    pause
    exit /b 1
)

echo.
echo [INFO] Waiting for health endpoint: %HEALTH_URL%
set /a TRIES=0

:HEALTH_WAIT
set /a TRIES+=1

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri '%HEALTH_URL%' -TimeoutSec 3 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Application is healthy.
    goto :STARTED
)

if !TRIES! geq %MAX_TRIES% (
    echo.
    echo [WARN] Health check timed out after !TRIES! attempts.
    echo [WARN] Showing recent container logs:
    !COMPOSE_CMD! logs --tail=120
    echo.
    echo [INFO] The app might still be starting. Continuing anyway.
    goto :STARTED
)

echo [INFO] Waiting... attempt !TRIES!/%MAX_TRIES%
timeout /t %WAIT_SECONDS% /nobreak >nul
goto :HEALTH_WAIT

:STARTED
echo.
echo [INFO] Running seed synchronization against configured Neon database...
!COMPOSE_CMD! exec -T app python scripts/seed_neon_db.py >nul 2>&1
if errorlevel 1 (
    echo [WARN] Seed sync command failed inside container.
    echo [WARN] App is running; you can seed manually with:
    echo        docker compose exec -T app python scripts/seed_neon_db.py
) else (
    echo [OK] Database seed synchronization completed.
)

echo.
echo ==================================================
echo   App URL : %APP_URL%
echo   Docs    : %DOCS_URL%
echo   DB      : Neon Postgres (from hospital-agent-system\.env)
echo ==================================================
echo.

start "" "%APP_URL%"
start "" "%DOCS_URL%"

echo [INFO] Containers are running in the background.
echo [INFO] To view logs later, run:
echo        !COMPOSE_CMD! logs --follow --tail=80
echo.
echo [DONE] Launch complete.

endlocal
