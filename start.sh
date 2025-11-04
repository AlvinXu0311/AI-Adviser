#!/bin/bash

# Start script for WPI Business School Chatbot
# Starts both frontend and backend services with LangChain agentic RAG
# Uses ReAct pattern for autonomous agent reasoning

echo "================================"
echo "WPI Chatbot - Start Services"
echo "LangChain Agentic RAG Enabled"
echo "================================"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo -e "${RED}✗ Node.js is not installed${NC}"
    echo "  Please install Node.js from https://nodejs.org"
    exit 1
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo -e "${RED}✗ Python is not installed${NC}"
    echo "  Please install Python from https://www.python.org"
    exit 1
fi

# Check if python3-venv is available
if ! python3 -m venv --help &> /dev/null; then
    echo -e "${RED}✗ python3-venv is not installed${NC}"
    echo "  Please install: sudo apt install python3-venv"
    exit 1
fi

# Check if pip is available, if not try to bootstrap it
if ! python3 -m pip --version &> /dev/null; then
    echo "Bootstrapping pip using ensurepip..."
    if ! python3 -m ensurepip --default-pip 2>&1; then
        echo -e "${YELLOW}⚠ Warning: Could not bootstrap pip${NC}"
        echo "  Attempting to install system pip..."
        if ! sudo apt-get update && sudo apt-get install -y python3-pip 2>&1 | grep -q "done"; then
            echo -e "${YELLOW}⚠ Warning: System pip installation may have failed${NC}"
            echo "  Will continue - pip may work in venv"
        fi
    else
        echo -e "${GREEN}✓ Pip bootstrapped successfully${NC}"
    fi
fi

echo -e "${GREEN}✓ Prerequisites check passed${NC}"
echo ""

# Kill any existing processes on ports 4200 and 8000 (optional)
# Uncomment to enable
# echo "Cleaning up old processes..."
# lsof -ti :4200 | xargs kill -9 2>/dev/null || true
# lsof -ti :8000 | xargs kill -9 2>/dev/null || true

# Create a temporary file to track process IDs
PIDFILE=".chatbot_pids"
rm -f $PIDFILE

# Start Backend
echo "Starting Backend (FastAPI on port 8000)..."
cd backend

# Check if virtual environment exists and is valid
VENV_VALID=0
if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
    VENV_VALID=1
fi

# If venv doesn't exist or is invalid, recreate it
if [ $VENV_VALID -eq 0 ]; then
    echo "Creating Python virtual environment..."
    # Remove broken venv if it exists
    if [ -d "venv" ]; then
        rm -rf venv
    fi

    if ! python3 -m venv venv; then
        echo -e "${RED}✗ Failed to create virtual environment${NC}"
        echo "  Make sure python3-venv is installed:"
        echo "  sudo apt install python3-venv"
        exit 1
    fi
fi

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
else
    echo -e "${RED}✗ Could not find venv activate script${NC}"
    echo "  The virtual environment may be corrupted."
    echo "  Try: rm -rf venv && python3 -m venv venv"
    exit 1
fi

# Check if dependencies are installed
if ! ./venv/bin/python -m pip show fastapi > /dev/null 2>&1; then
    echo "Installing backend dependencies..."
    if ! ./venv/bin/pip install -r requirements.txt; then
        echo -e "${RED}✗ Failed to install backend dependencies${NC}"
        echo "  Check your internet connection and try again"
        exit 1
    fi
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo ""
    echo -e "${YELLOW}Warning: .env file not found${NC}"
    echo "  Copy .env.example to .env and set GOOGLE_API_KEY:"
    echo "  cp .env.example .env"
    echo "  # Edit .env and add your Google Gemini API key"
    echo ""
fi

# Verify LangChain dependencies
echo "Checking LangChain dependencies..."
if ! ./venv/bin/python -c "import langchain" 2>/dev/null; then
    echo "Installing LangChain framework..."
    if ! ./venv/bin/pip install langchain langchain-google-genai langchain-community chromadb sentence-transformers rank-bm25; then
        echo -e "${YELLOW}Warning: Some LangChain dependencies may not have installed correctly${NC}"
    fi
fi

echo -e "${GREEN}LangChain framework ready${NC}"
echo ""

# Start backend in background
./venv/bin/python -m uvicorn app.main:app --reload --port 8000 > "../backend.log" 2>&1 &
BACKEND_PID=$!

# Give it a moment to start and check if it's still running
sleep 1
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${RED}✗ Backend failed to start${NC}"
    echo "  Check backend.log for details:"
    cat ../backend.log
    exit 1
fi

echo $BACKEND_PID >> "../$PIDFILE"
echo -e "${GREEN}✓ Backend started (PID: $BACKEND_PID)${NC}"

cd ..

# Start Frontend
echo ""
echo "Starting Frontend (Angular on port 4200)..."
cd frontend

# Check if dependencies are installed
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# Start frontend in background
npm start > "../frontend.log" 2>&1 &
FRONTEND_PID=$!

# Give it a moment to start (frontend takes longer to compile)
sleep 3
if ! kill -0 $FRONTEND_PID 2>/dev/null; then
    echo -e "${RED}✗ Frontend failed to start${NC}"
    echo "  Check frontend.log for details:"
    tail -20 ../frontend.log
    exit 1
fi

echo $FRONTEND_PID >> "../$PIDFILE"
echo -e "${GREEN}✓ Frontend started (PID: $FRONTEND_PID)${NC}"

cd ..

echo ""
echo "================================"
echo -e "${GREEN}Services Started Successfully${NC}"
echo "================================"
echo ""
echo "Access Points:"
echo "  Frontend:  http://localhost:4200"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo "  Health:    http://localhost:8000/api/health"
echo ""
echo "LangChain Agentic RAG:"
echo "  Adviser Agent:       Autonomous reasoning with ReAct pattern"
echo "  Hybrid RAG:          BM25 + Semantic search with ensemble"
echo "  Tools:               RAG Search, Student Context, Complexity Analysis"
echo "  Vector Database:     Chroma (for embeddings)"
echo ""
echo "Logs:"
echo "  Backend log:   tail -f backend.log"
echo "  Frontend log:  tail -f frontend.log"
echo ""
echo "To stop services:"
echo "  Press Ctrl+C (stops both)"
echo "  Or run: ./stop.sh"
echo ""
echo "Backend is ready! Check logs above for any errors."
echo ""

# Keep script running and show logs
tail -f backend.log frontend.log
