#!/bin/bash

# =============================================================================
# WPI Business School Chatbot - Local Development (Foreground)
# =============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=3000

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "================================"
echo "WPI Chatbot - Local Development"
echo "================================"
echo ""

# Cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}[Stopping all services...]${NC}"
    pkill -9 -f "uvicorn" 2>/dev/null
    pkill -9 -f "vite" 2>/dev/null
    pkill -9 -f "node.*frontend" 2>/dev/null
    for PORT in $BACKEND_PORT $FRONTEND_PORT 5173 5174; do
        kill -9 $(lsof -ti :$PORT) 2>/dev/null
    done
    echo -e "${GREEN}Done.${NC}"
    exit 0
}
trap cleanup INT TERM

# =============================================================================
# Step 1: Clean up existing processes
# =============================================================================
echo "[Step 1/4] Cleaning up..."

# Kill processes by name
echo "  Stopping existing processes..."
pkill -9 -f "uvicorn" 2>/dev/null || true
pkill -9 -f "vite" 2>/dev/null || true
pkill -9 -f "node.*frontend" 2>/dev/null || true
pkill -9 -f "python.*app.main" 2>/dev/null || true

# Clean up ports - try multiple methods
echo "  Freeing ports..."
for PORT in $BACKEND_PORT $FRONTEND_PORT 5173 5174; do
    # Method 1: lsof
    PIDS=$(lsof -ti :$PORT 2>/dev/null)
    if [ -n "$PIDS" ]; then
        for PID in $PIDS; do
            kill -9 $PID 2>/dev/null || true
            echo "    Killed PID $PID on port $PORT"
        done
    fi

    # Method 2: fuser (fallback)
    if lsof -ti :$PORT >/dev/null 2>&1; then
        fuser -k -9 $PORT/tcp 2>/dev/null || true
        echo "    Force freed port $PORT"
    fi
done

sleep 2
echo -e "  ${GREEN}Cleanup complete${NC}"

# =============================================================================
# Step 2: Check prerequisites
# =============================================================================
echo ""
echo "[Step 2/4] Checking prerequisites..."

# Check Redis
if ! redis-cli ping > /dev/null 2>&1; then
    echo -e "  ${YELLOW}Redis not running, starting...${NC}"
    sudo systemctl start redis-server 2>/dev/null || sudo service redis-server start 2>/dev/null
    sleep 1
    if ! redis-cli ping > /dev/null 2>&1; then
        echo -e "  ${RED}✗ Failed to start Redis${NC}"
        echo "  Please install/start Redis: sudo apt install redis-server && sudo systemctl start redis-server"
        exit 1
    fi
fi
echo -e "  ${GREEN}✓ Redis running${NC}"

BACKEND_VENV="$PROJECT_DIR/backend/venv"
if [ ! -d "$BACKEND_VENV" ]; then
    echo "  Creating Python venv..."
    python3 -m venv "$BACKEND_VENV"
fi

if ! "$BACKEND_VENV/bin/python" -m pip show fastapi > /dev/null 2>&1; then
    echo "  Installing backend dependencies..."
    "$BACKEND_VENV/bin/pip" install -q -r "$PROJECT_DIR/backend/requirements.txt"
fi

# Ensure frontend has local backend URL
echo "VITE_BACKEND_URL=http://localhost:$BACKEND_PORT" > "$PROJECT_DIR/frontend/.env"

echo -e "  ${GREEN}Prerequisites OK${NC}"

# =============================================================================
# Step 3: Start Backend (background)
# =============================================================================
echo ""
echo "[Step 3/4] Starting Backend (port $BACKEND_PORT)..."
cd "$PROJECT_DIR/backend"
source venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port $BACKEND_PORT > "$PROJECT_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

sleep 2
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "  ${RED}Backend failed to start${NC}"
    cat "$PROJECT_DIR/backend.log"
    exit 1
fi
echo -e "  ${GREEN}Backend started (PID: $BACKEND_PID)${NC}"

# =============================================================================
# Step 4: Start Frontend (foreground)
# =============================================================================
echo ""
echo "[Step 4/4] Starting Frontend (port $FRONTEND_PORT)..."
cd "$PROJECT_DIR/frontend"

if [ ! -d "node_modules" ]; then
    echo "  Installing frontend dependencies..."
    npm install
fi

echo ""
echo "================================"
echo -e "${GREEN}Services Starting...${NC}"
echo "================================"
echo ""
echo "Access Points:"
echo "  Frontend:  http://localhost:$FRONTEND_PORT"
echo "  Backend:   http://localhost:$BACKEND_PORT"
echo "  API Docs:  http://localhost:$BACKEND_PORT/docs"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""
echo "================================"
echo ""

# Run frontend in foreground (blocking)
npm run dev -- --host 0.0.0.0
