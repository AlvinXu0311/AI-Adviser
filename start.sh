
# --- Start script (simplified) ---
echo "Starting Backend (FastAPI on port 8000)..."

# Resolve repo root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# Paths
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
BACKEND_VENV="$BACKEND_DIR/venv"
PIDFILE="$REPO_ROOT/.chatbot_pids"

if [ ! -d "$BACKEND_DIR" ]; then
    echo -e "${RED}✗ Could not find backend directory at $BACKEND_DIR${NC}"
    exit 1
fi

# Create PID file tracking
rm -f "$PIDFILE"

# Create backend venv if missing (do NOT create symlinks)
if [ ! -d "$BACKEND_VENV" ] || [ ! -f "$BACKEND_VENV/bin/activate" ]; then
    echo "backend venv not found. Creating $BACKEND_VENV..."
    if ! python3 -m venv "$BACKEND_VENV"; then
        echo -e "${RED}✗ Failed to create backend venv at $BACKEND_VENV${NC}"
        echo "  Make sure python3-venv is installed: sudo apt install python3-venv"
        exit 1
    fi
    echo "Created backend venv at $BACKEND_VENV"
fi

# Install backend requirements (non-blocking failures are warned)
if ! "$BACKEND_VENV/bin/python" -m pip show fastapi > /dev/null 2>&1; then
    echo "Installing backend dependencies into $BACKEND_VENV from backend/requirements.txt..."
    "$BACKEND_VENV/bin/pip" install --upgrade pip setuptools wheel || true
    REQ_FILE="$BACKEND_DIR/requirements.txt"
    if [ ! -f "$REQ_FILE" ]; then
        REQ_FILE="$REPO_ROOT/requirements.txt"
    fi
    if ! "$BACKEND_VENV/bin/pip" install -r "$REQ_FILE"; then
        echo -e "${YELLOW}⚠ Warning: Some backend dependencies failed to install into $BACKEND_VENV${NC}"
        echo "  You can try: source $BACKEND_VENV/bin/activate && pip install -r $REQ_FILE"
    fi
fi

# Activate backend venv
# shellcheck disable=SC1090
source "$BACKEND_VENV/bin/activate"

echo -e "${GREEN}Prerequisites check passed${NC}"
echo ""

# Start Backend
echo "Starting Backend (FastAPI on port 8000)..."
cd "$BACKEND_DIR" || exit 1

"$BACKEND_VENV/bin/python" -m uvicorn app.main:app --reload --port 8000 > "$REPO_ROOT/backend.log" 2>&1 &
BACKEND_PID=$!

# Give it a moment to start and check if it's still running
sleep 1
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${RED}✗ Backend failed to start${NC}"
    echo "  Check backend.log for details:"
    cat "$REPO_ROOT/backend.log"
    exit 1
fi

echo $BACKEND_PID >> "$PIDFILE"
echo -e "${GREEN}Backend started (PID: $BACKEND_PID)${NC}"

cd "$REPO_ROOT" || exit 1

# Start Frontend
echo ""
echo "Starting Frontend (React/Vite on port 5173)..."
cd frontend

# Check if dependencies are installed
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# Start frontend in background (Vite dev server)
npm run dev -- --host 0.0.0.0 --port 5173 > "../frontend.log" 2>&1 &
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
echo "  Frontend:  http://localhost:5173"
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
