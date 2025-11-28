#!/bin/bash

# =============================================================================
# AI-Adviser Cloudflare Tunnel Deployment (Background)
# Creates public URLs for sharing
# =============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=3000
PIDFILE="$PROJECT_DIR/.tunnel_pids"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo "========================================"
echo "  AI-Adviser Tunnel Deployment"
echo "========================================"
echo ""

# =============================================================================
# Step 1: Clean up existing processes
# =============================================================================
echo "[Step 1/5] Cleaning up..."
pkill -9 -f "uvicorn" 2>/dev/null || true
pkill -9 -f "vite" 2>/dev/null || true
pkill -9 -f "cloudflared" 2>/dev/null || true
pkill -9 -f "node.*frontend" 2>/dev/null || true

for PORT in $BACKEND_PORT $FRONTEND_PORT 5173 5174 4040; do
    PID=$(lsof -ti :$PORT 2>/dev/null)
    if [ -n "$PID" ]; then
        kill -9 $PID 2>/dev/null
        echo "  Freed port $PORT"
    fi
done
rm -f "$PIDFILE"
sleep 2
echo -e "  ${GREEN}Done${NC}"

# =============================================================================
# Step 1.5: Check Redis
# =============================================================================
echo ""
echo "Checking Redis..."
if ! redis-cli ping > /dev/null 2>&1; then
    echo -e "  ${YELLOW}Redis not running, starting...${NC}"
    sudo systemctl start redis-server 2>/dev/null || sudo service redis-server start 2>/dev/null
    sleep 1
    if ! redis-cli ping > /dev/null 2>&1; then
        echo -e "  ${RED}✗ Failed to start Redis${NC}"
        exit 1
    fi
fi
echo -e "  ${GREEN}✓ Redis running${NC}"

# =============================================================================
# Step 2: Start Backend (with ALLOW_ALL_ORIGINS for tunnel)
# =============================================================================
echo ""
echo "[Step 2/5] Starting Backend..."
cd "$PROJECT_DIR/backend"
source venv/bin/activate
ALLOW_ALL_ORIGINS=true python -m uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT > "$PROJECT_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID >> "$PIDFILE"

# Wait for backend
for i in {1..30}; do
    if curl -s http://localhost:$BACKEND_PORT/ > /dev/null 2>&1; then
        echo -e "  ${GREEN}Backend ready (PID: $BACKEND_PID)${NC}"
        break
    fi
    sleep 1
done

# =============================================================================
# Step 3: Create Backend tunnel
# =============================================================================
echo ""
echo "[Step 3/5] Creating Backend tunnel..."
cloudflared tunnel --url http://localhost:$BACKEND_PORT > "$PROJECT_DIR/tunnel-backend.log" 2>&1 &
TUNNEL_BACKEND_PID=$!
echo $TUNNEL_BACKEND_PID >> "$PIDFILE"
sleep 5

# Get backend URL
BACKEND_URL=""
for i in {1..15}; do
    BACKEND_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$PROJECT_DIR/tunnel-backend.log" 2>/dev/null | head -1)
    if [ -n "$BACKEND_URL" ]; then
        break
    fi
    sleep 1
done

if [ -z "$BACKEND_URL" ]; then
    echo -e "  ${RED}[ERROR] Could not get backend tunnel URL${NC}"
    cat "$PROJECT_DIR/tunnel-backend.log"
    exit 1
fi
echo -e "  ${GREEN}Backend URL: $BACKEND_URL${NC}"

# =============================================================================
# Step 4: Start Frontend with tunnel backend URL
# =============================================================================
echo ""
echo "[Step 4/5] Starting Frontend..."
echo "VITE_BACKEND_URL=$BACKEND_URL" > "$PROJECT_DIR/frontend/.env"
cd "$PROJECT_DIR/frontend"

if [ ! -d "node_modules" ]; then
    npm install
fi

npm run dev -- --host 0.0.0.0 > "$PROJECT_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID >> "$PIDFILE"

# Wait for frontend
for i in {1..30}; do
    if grep -q "localhost:$FRONTEND_PORT" "$PROJECT_DIR/frontend.log" 2>/dev/null; then
        echo -e "  ${GREEN}Frontend ready (PID: $FRONTEND_PID)${NC}"
        break
    fi
    sleep 1
done

# =============================================================================
# Step 5: Create Frontend tunnel
# =============================================================================
echo ""
echo "[Step 5/5] Creating Frontend tunnel..."
cloudflared tunnel --url http://localhost:$FRONTEND_PORT > "$PROJECT_DIR/tunnel-frontend.log" 2>&1 &
TUNNEL_FRONTEND_PID=$!
echo $TUNNEL_FRONTEND_PID >> "$PIDFILE"
sleep 5

# Get frontend URL
FRONTEND_URL=""
for i in {1..15}; do
    FRONTEND_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$PROJECT_DIR/tunnel-frontend.log" 2>/dev/null | head -1)
    if [ -n "$FRONTEND_URL" ]; then
        break
    fi
    sleep 1
done

if [ -z "$FRONTEND_URL" ]; then
    echo -e "  ${YELLOW}[WARNING] Could not get frontend tunnel URL${NC}"
    FRONTEND_URL="(failed)"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "========================================"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo "========================================"
echo ""
echo -e "${CYAN}  Public URLs (share these!):${NC}"
echo "    Frontend: $FRONTEND_URL"
echo "    Backend:  $BACKEND_URL"
echo ""
echo "  Local URLs:"
echo "    Frontend: http://localhost:$FRONTEND_PORT"
echo "    Backend:  http://localhost:$BACKEND_PORT"
echo ""
echo "========================================"

# Save URLs
cat > "$PROJECT_DIR/deployment-urls.txt" << EOF
AI-Adviser Public URLs
$(date)

Frontend: $FRONTEND_URL
Backend:  $BACKEND_URL
EOF

echo ""
echo -e "${GREEN}Tunnels running in background.${NC}"
echo "URLs saved to deployment-urls.txt"
echo ""
echo "To stop: ./stop.sh"
echo "To view logs: tail -f backend.log frontend.log tunnel-*.log"
echo ""
