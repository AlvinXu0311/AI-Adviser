p#!/bin/bash

# =============================================================================
# WPI Chatbot - Stop All Services
# Stops: backend, frontend, cloudflared tunnels, and frees all ports
# =============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "================================"
echo "WPI Chatbot - Stop All Services"
echo "================================"
echo ""

# =============================================================================
# Kill by process name
# =============================================================================
echo "Stopping processes..."

pkill -9 -f "uvicorn" 2>/dev/null && echo -e "  ${GREEN}✓ Stopped: uvicorn${NC}" || echo -e "  ${YELLOW}- uvicorn not running${NC}"
pkill -9 -f "vite" 2>/dev/null && echo -e "  ${GREEN}✓ Stopped: vite${NC}" || echo -e "  ${YELLOW}- vite not running${NC}"
pkill -9 -f "node.*frontend" 2>/dev/null
pkill -9 -f "cloudflared" 2>/dev/null && echo -e "  ${GREEN}✓ Stopped: cloudflared${NC}" || echo -e "  ${YELLOW}- cloudflared not running${NC}"

# Stop Redis (systemd service or process)
if systemctl is-active --quiet redis-server 2>/dev/null; then
    sudo systemctl stop redis-server 2>/dev/null && echo -e "  ${GREEN}✓ Stopped: redis-server (systemd)${NC}" || echo -e "  ${YELLOW}- Failed to stop redis-server (need sudo)${NC}"
elif pgrep -f "redis-server" > /dev/null 2>&1; then
    pkill -9 -f "redis-server" 2>/dev/null && echo -e "  ${GREEN}✓ Stopped: redis-server${NC}" || echo -e "  ${YELLOW}- redis-server requires sudo to stop${NC}"
else
    echo -e "  ${YELLOW}- redis-server not running${NC}"
fi

# =============================================================================
# Kill by port (all possible ports)
# =============================================================================
echo ""
echo "Freeing ports..."

PORTS_TO_CHECK="3000 5173 5174 8000 4040 6379"
for PORT in $PORTS_TO_CHECK; do
    PID=$(lsof -ti :$PORT 2>/dev/null)
    if [ -n "$PID" ]; then
        kill -9 $PID 2>/dev/null
        echo -e "  ${GREEN}✓ Freed port $PORT (PID: $PID)${NC}"
    fi
done

# =============================================================================
# Clean up files
# =============================================================================
rm -f "$PROJECT_DIR/.chatbot_pids" "$PROJECT_DIR/.tunnel_pids" 2>/dev/null

# Wait for cleanup
sleep 1

# =============================================================================
# Verify all ports are free
# =============================================================================
echo ""
echo "Verifying ports..."
ALL_FREE=true

for PORT in 3000 5173 8000 6379; do
    if lsof -i :$PORT > /dev/null 2>&1; then
        echo -e "  ${RED}✗ Port $PORT: still in use${NC}"
        ALL_FREE=false
    else
        echo -e "  ${GREEN}✓ Port $PORT: free${NC}"
    fi
done

echo ""
echo "================================"
if [ "$ALL_FREE" = true ]; then
    echo -e "${GREEN}All Services Stopped${NC}"
else
    echo -e "${YELLOW}Some ports still in use - try running again${NC}"
fi
echo "================================"
echo ""
