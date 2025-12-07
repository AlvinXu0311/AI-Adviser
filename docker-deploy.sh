#!/bin/bash

# WPI AI Adviser - Docker Deployment Script
# Supports: Linux, macOS, Windows (Git Bash/WSL)

set -e

# Detect operating system
OS="$(uname -s)"
case "${OS}" in
    Linux*)     OS_TYPE=Linux;;
    Darwin*)    OS_TYPE=Mac;;
    CYGWIN*|MINGW*|MSYS*)    OS_TYPE=Windows;;
    *)          OS_TYPE="UNKNOWN"
esac

echo "[INFO] Detected OS: ${OS_TYPE}"

# Check if we need sudo for Docker (Linux only)
DOCKER_CMD="docker"
COMPOSE_CMD="docker-compose"

# On Linux, check if we need sudo
if [ "${OS_TYPE}" = "Linux" ]; then
    if ! docker ps > /dev/null 2>&1; then
        echo "[INFO] Docker requires sudo permissions on Linux"
        DOCKER_CMD="sudo docker"
        COMPOSE_CMD="sudo docker-compose"
    fi
fi

# On Mac/Windows, Docker Desktop handles permissions
if [ "${OS_TYPE}" = "Mac" ] || [ "${OS_TYPE}" = "Windows" ]; then
    if ! docker ps > /dev/null 2>&1; then
        echo "[ERROR] Docker is not running. Please start Docker Desktop first."
        exit 1
    fi
fi

echo "======================================"
echo "WPI AI Adviser - Docker Deployment"
echo "======================================"

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "[WARN] .env file not found!"
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "[SUCCESS] Created .env file. Please edit it with your GOOGLE_API_KEY."
    echo "Then run this script again."
    exit 1
fi

# Check if GOOGLE_API_KEY is set
if ! grep -q "GOOGLE_API_KEY=.*[^=]" .env; then
    echo "[ERROR] GOOGLE_API_KEY is not set in .env file!"
    echo "Please edit .env and add your Google API key."
    exit 1
fi

# Stop any running containers
echo ""
echo "Stopping existing containers..."
$COMPOSE_CMD down

# Build and start services
echo ""
echo "Building Docker images..."
$COMPOSE_CMD build

echo ""
echo "Starting services..."
$COMPOSE_CMD up -d

# Wait for services to be healthy
echo ""
echo "Waiting for services to be healthy..."
sleep 10

# Check service status
echo ""
echo "Service Status:"
$COMPOSE_CMD ps

echo ""
echo "Health Checks:"
echo "  - Redis: $($COMPOSE_CMD exec -T redis redis-cli ping 2>/dev/null || echo 'FAILED')"
echo "  - Backend: $(curl -s http://localhost:8000/api/status | grep -o '"overall_status":"[^"]*"' || echo 'FAILED')"
echo "  - Frontend: $(curl -s -o /dev/null -w "%{http_code}" http://localhost/ || echo 'FAILED')"

echo ""
echo "Deployment complete!"
echo ""
echo "Access the application:"
echo "  - Frontend: http://localhost"
echo "  - Backend API: http://localhost:8000"
echo "  - API Status: http://localhost:8000/api/status"
echo ""
echo "View logs:"
echo "  $COMPOSE_CMD logs -f"
echo ""
echo "Stop services:"
echo "  $COMPOSE_CMD down"
