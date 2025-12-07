@echo off
REM WPI AI Adviser - Docker Deployment Script for Windows
REM Requires: Docker Desktop for Windows

echo ======================================
echo WPI AI Adviser - Docker Deployment
echo ======================================

REM Check if Docker is running
docker ps >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running. Please start Docker Desktop first.
    pause
    exit /b 1
)

REM Check if .env file exists
if not exist ".env" (
    echo [WARN] .env file not found!
    echo Creating .env from .env.example...
    copy .env.example .env
    echo [SUCCESS] Created .env file. Please edit it with your GOOGLE_API_KEY.
    echo Then run this script again.
    pause
    exit /b 1
)

REM Check if GOOGLE_API_KEY is set
findstr /R "GOOGLE_API_KEY=.*[^=]" .env >nul 2>&1
if errorlevel 1 (
    echo [ERROR] GOOGLE_API_KEY is not set in .env file!
    echo Please edit .env and add your Google API key.
    pause
    exit /b 1
)

REM Stop any running containers
echo.
echo Stopping existing containers...
docker-compose down

REM Build and start services
echo.
echo Building Docker images...
docker-compose build

echo.
echo Starting services...
docker-compose up -d

REM Wait for services to be healthy
echo.
echo Waiting for services to be healthy...
timeout /t 10 /nobreak >nul

REM Check service status
echo.
echo Service Status:
docker-compose ps

echo.
echo Health Checks:
docker-compose exec -T redis redis-cli ping 2>nul || echo   - Redis: FAILED
curl -s http://localhost:8000/api/status | findstr "overall_status" || echo   - Backend: FAILED
curl -s -o nul -w "%%{http_code}" http://localhost/ || echo   - Frontend: FAILED

echo.
echo Deployment complete!
echo.
echo Access the application:
echo   - Frontend: http://localhost
echo   - Backend API: http://localhost:8000
echo   - API Status: http://localhost:8000/api/status
echo.
echo View logs:
echo   docker-compose logs -f
echo.
echo Stop services:
echo   docker-compose down
echo.
pause
