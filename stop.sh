#!/bin/bash

# Stop script for WPI Business School Chatbot
# Stops both frontend and backend services

echo "================================"
echo "WPI Chatbot - Stop Services"
echo "================================"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PIDFILE=".chatbot_pids"

# Check if PID file exists
if [ ! -f "$PIDFILE" ]; then
    echo -e "${YELLOW}No process ID file found${NC}"
    echo "Attempting to kill processes on ports 4200 and 8000..."

    # Try to kill processes on specific ports
    if command -v lsof &> /dev/null; then
        # Kill process on port 4200 (Frontend)
        FRONTEND_PID=$(lsof -ti :4200)
        if [ ! -z "$FRONTEND_PID" ]; then
            kill -9 $FRONTEND_PID 2>/dev/null
                echo -e "${GREEN}Stopped Frontend (PID: $FRONTEND_PID)${NC}"
        fi

        # Kill process on port 8000 (Backend)
        BACKEND_PID=$(lsof -ti :8000)
        if [ ! -z "$BACKEND_PID" ]; then
            kill -9 $BACKEND_PID 2>/dev/null
            echo -e "${GREEN}Stopped Backend (PID: $BACKEND_PID)${NC}"
        fi
    else
        echo -e "${YELLOW}lsof not found, trying alternative method...${NC}"
        # For Windows or systems without lsof
        if command -v netstat &> /dev/null; then
            echo "Found processes, attempting to kill..."
            # Try pkill if available
            if command -v pkill &> /dev/null; then
                pkill -f "ng serve" 2>/dev/null
                pkill -f "uvicorn" 2>/dev/null
                echo -e "${GREEN}Killed processes${NC}"
            fi
        fi
    fi
else
    echo "Stopping processes from $PIDFILE..."

    # Read PIDs from file
    while IFS= read -r PID; do
        if [ ! -z "$PID" ]; then
            if ps -p $PID > /dev/null 2>&1; then
                kill -9 $PID 2>/dev/null
                echo -e "${GREEN}Stopped process (PID: $PID)${NC}"
            else
                echo -e "${YELLOW}Process $PID not found${NC}"
            fi
        fi
    done < "$PIDFILE"

    # Remove PID file
    rm -f "$PIDFILE"
    echo "Process ID file removed"
fi

echo ""
echo "================================"
echo -e "${GREEN}Services Stopped${NC}"
echo "================================"
echo ""
echo "Port 4200 (Frontend):  Available"
echo "Port 8000 (Backend):   Available"
echo ""
