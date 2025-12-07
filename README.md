# WPI Business School Digital Adviser

Interactive chatbot platform for academic advising with PDF transcript upload, LangChain agents, and Database-First architecture.

## Quick Start

### Prerequisites

- **Option 1: Docker (Recommended for Production)**
  - Docker Engine 20.10+
  - Docker Compose 1.29+
  - Google Gemini API key

- **Option 2: Local Development**
  - Node.js 16+ (for frontend)
  - Python 3.8+ (for backend)
  - Google Gemini API key

### Option 1: Docker Deployment (Recommended)

**Step 1: Install Docker**
- **Linux**: Install Docker Engine and Docker Compose
- **macOS**: Install [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
- **Windows**: Install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)

**Step 2: Deploy**

```bash
# 1. Clone the repository
git clone <repository-url>
cd AI-Adviser

# 2. Configure environment
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

# 3. Deploy with Docker Compose
./docker-deploy.sh
# Or manually: docker-compose up -d
# On Windows Git Bash: bash docker-deploy.sh

# 4. Access the application
# - Frontend: http://localhost
# - Backend API: http://localhost:8000
# - API Status: http://localhost:8000/api/status

# Stop services
docker-compose down
# Or: sudo docker-compose down (Linux with sudo)
```

**Platform-Specific Notes:**
- **Linux**: Script auto-detects if sudo is needed
- **macOS/Windows**: Ensure Docker Desktop is running before deployment
- **Windows Users**:
  - Option 1: Double-click `docker-deploy.bat` in File Explorer
  - Option 2: Run `bash docker-deploy.sh` in Git Bash
  - Option 3: Use WSL (Windows Subsystem for Linux)

**Docker Services:**
- **Frontend**: React + Nginx (Port 80)
- **Backend**: FastAPI + Python (Port 8000)
- **Redis**: Session management (Port 6379)

**Docker Commands:**
```bash
# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f backend

# Check service status
docker-compose ps

# Rebuild and restart
docker-compose build && docker-compose up -d

# Stop and remove all containers
docker-compose down -v
```

### Option 2: Local Development Start

**Automatic (Recommended):**
```bash
# Make scripts executable (first time only)
chmod +x start.sh stop.sh

# Start both services (backend + frontend)
./start.sh

# Stop both services when done
./stop.sh
```

**Manual:**

**Terminal 1: Backend**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add GOOGLE_API_KEY
python -m uvicorn app.main:app --reload
```

**Terminal 2: Frontend**
```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

**Access the Application:**
- **Frontend** (Local): http://localhost:5173
- **Frontend** (Docker): http://localhost
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **API Status**: http://localhost:8000/api/status

## Architecture Overview

### Application Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                   Frontend (React + Nginx)                       │
│  - Chat Interface with streaming responses                       │
│  - PDF transcript upload with Gemini Vision extraction           │
│  - Real-time system status indicators                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Backend (FastAPI)                            │
│                                                                  │
│  ┌─────────────────┐    ┌──────────────────────────────────┐   │
│  │  Intent Agent   │───▶│       Adviser Agent (ReAct)       │   │
│  │  (Free-form LLM │    │  - business_school_database tool  │   │
│  │   Classification)    │  - context_lookup tool            │   │
│  └─────────────────┘    │  - semantic_search tool           │   │
│                         └──────────────────────────────────┘   │
│                                      │                          │
│                                      ▼                          │
│         ┌──────────────────┐    ┌─────────────────────┐        │
│         │ SQLite Database  │    │ ChromaDB Vector DB  │        │
│         │ (bus_school.db)  │    │  (semantic search)  │        │
│         │  - Programs (3)  │    │  - Courses (103)    │        │
│         │  - Specialties(7)│    │  - Programs (3)     │        │
│         │  - Courses (103) │    │  - Specialties (7)  │        │
│         └──────────────────┘    └─────────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │      Redis       │
                    │ (Session Memory) │
                    └──────────────────┘
```

### Docker Deployment Architecture
```
┌──────────────────────────────────────────────────────────────┐
│                      Docker Host                              │
│                                                               │
│  ┌────────────────────┐  ┌────────────────────┐             │
│  │   frontend:80      │  │   backend:8000     │             │
│  │  (nginx + react)   │──│  (FastAPI+Python)  │             │
│  └────────────────────┘  └────────────────────┘             │
│                                    │                          │
│                          ┌─────────┴─────────┐               │
│                          │                   │               │
│                    ┌─────▼──────┐    ┌──────▼─────┐         │
│                    │ redis:6379 │    │ Volumes:   │         │
│                    │  (cache)   │    │ - vector_db│         │
│                    └────────────┘    │ - redis_data│        │
│                                      └────────────┘         │
└──────────────────────────────────────────────────────────────┘
```

## Project Structure

```
AI-Adviser/
├── frontend/                          # React (Vite) application
│   ├── components/
│   │   ├── ChatInterface.tsx         # Main chat UI
│   │   ├── MessageBubble.tsx         # Message display with markdown
│   │   ├── InputArea.tsx             # Text input + file upload + voice
│   │   ├── Header.tsx                # Top navigation bar
│   │   └── Sidebar.tsx               # Side panel with real-time status
│   ├── services/
│   │   ├── chatService.ts            # API client (streaming + transcript)
│   │   └── statusService.ts          # System status API client
│   ├── assets/
│   │   └── WPI_ICON.jpg              # WPI logo
│   ├── App.tsx                       # Application shell
│   ├── types.ts                      # TypeScript types
│   ├── constants.ts                  # App constants
│   ├── Dockerfile                    # Multi-stage build (Node + Nginx)
│   ├── nginx.conf                    # Nginx configuration
│   └── .dockerignore                 # Docker ignore patterns
│
├── backend/                           # FastAPI application
│   ├── app/
│   │   ├── agents/
│   │   │   ├── adviser_agent.py      # ReAct agent with tool use
│   │   │   ├── intent_agent.py       # Intent classification
│   │   │   ├── tools.py              # Agent tools (db, search, context)
│   │   │   └── streaming_callback.py # SSE streaming handler
│   │   ├── api/
│   │   │   ├── chat.py               # /api/chat endpoint (streaming)
│   │   │   ├── transcript.py         # /api/extract-transcript
│   │   │   └── status.py             # /api/status (system health)
│   │   ├── services/
│   │   │   ├── program_db_service.py # SQLite database queries
│   │   │   ├── vector_search_service.py # ChromaDB semantic search
│   │   │   ├── context_manager.py    # Session-isolated context with TTL/LRU
│   │   │   ├── pdf_extraction_service.py # Gemini Vision PDF extraction
│   │   │   └── conversation_memory.py # Redis chat history with TTL
│   │   ├── schemas/
│   │   │   ├── chat.py               # Chat request/response models
│   │   │   └── transcript.py         # Transcript data models
│   │   └── main.py                   # FastAPI app setup
│   ├── tests/                        # Pytest test suite
│   ├── requirements.txt              # Python dependencies
│   ├── Dockerfile                    # Python 3.12-slim build
│   ├── .dockerignore                 # Docker ignore patterns
│   └── .env.example                  # Environment template
│
├── database/
│   ├── database_project/
│   │   ├── bus_school.db             # SQLite database (source of truth)
│   │   ├── setup_database.sql        # Database schema
│   │   └── wbs-courses.csv           # Course data
│   └── vector_db/                    # ChromaDB persistence (Docker volume)
│       └── chroma.sqlite3            # Vector database file
│
├── docker-compose.yml                # Multi-service orchestration
├── .env.example                      # Environment variables template
├── docker-deploy.sh                  # Docker deployment script (Linux/Mac)
├── docker-deploy.bat                 # Docker deployment script (Windows)
├── docker-test.sh                    # Docker configuration validator
├── start.sh                          # Local development start script
├── stop.sh                           # Local development stop script
└── README.md                         # This file
```

## Features

### Chat Interface
- **Streaming responses** - Real-time token-by-token output
- **Agent process visualization** - See tool calls and reasoning steps
- **Voice input** - Speech-to-text for questions
- **File upload** - PDF transcript extraction

### Intent Classification (Layer 1)
- **Free-form LLM analysis** - No hardcoded intent types
- **Confidence scoring** - 0.0-1.0 scale
- **Academic detection** - Filters non-academic queries
- **Transcript awareness** - Detects personal progress questions

### Adviser Agent (Layer 2)
- **ReAct pattern** - Thought → Action → Observation loop
- **Database-First** - SQLite as single source of truth
- **Tool use** - Automatic tool invocation based on query type

### Agent Tools

| Tool | Purpose | Example Queries |
|------|---------|-----------------|
| `business_school_database` | Query programs, specialties, courses | "What are MSIT requirements?" |
| `student_context` | Access uploaded transcript data | "What's my GPA?", "What courses have I taken?" |
| `assess_complexity` | Analyze query complexity | Internal routing decisions |

### Session Management & Context Isolation
- **Session-based isolation** - Each user session has completely isolated context
- **Redis conversation memory** - Chat history persisted in Redis with configurable TTL
- **TTL expiration** - Sessions auto-expire after 24 hours (configurable)
- **LRU eviction** - Oldest sessions evicted when max capacity reached
- **Tool context propagation** - Agent tools access session context via contextvars

### PDF Transcript Extraction
- **Gemini Vision API** - OCR + LLM extraction
- **Structured output** - Student name, ID, GPA, courses, grades
- **Session-scoped caching** - Transcript data isolated per session with TTL

## API Endpoints

### POST /api/chat
Stream chat responses with agent reasoning.

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the MSIT specializations?", "session_id": "abc123"}'
```

**Response**: Server-Sent Events (SSE) stream
```
data: {"type": "token", "content": "The "}
data: {"type": "token", "content": "MSIT "}
data: {"type": "tool_start", "tool_name": "business_school_database"}
data: {"type": "tool_end", "output": "..."}
data: {"type": "final", "content": "The MSIT program offers..."}
```

### POST /api/extract-transcript
Extract data from PDF transcript.

```bash
curl -X POST http://localhost:8000/api/extract-transcript \
  -H "Content-Type: application/json" \
  -d '{"pdf_base64": "JVBERi0xLjQK..."}'
```

**Response**:
```json
{
  "success": true,
  "data": {
    "student_name": "John Doe",
    "student_id": "A00123456",
    "gpa": 3.85,
    "program_info": {"program_name": "Information Technology (MS)"},
    "completed_courses": [...],
    "current_courses": [...]
  }
}
```

### GET /api/health
Health check endpoint.

```bash
curl http://localhost:8000/api/health
```

## Configuration

### Environment Variables

Create a `.env` file in the project root (copy from `.env.example`):

```bash
# Google API Configuration
GOOGLE_API_KEY=your_google_api_key_here

# LLM Provider (google or llama)
LLM_PROVIDER=google

# Gemini Model
GEMINI_MODEL=gemini-2.5-flash

# Redis Configuration
REDIS_HOST=redis              # Use 'redis' for Docker, 'localhost' for local
REDIS_PORT=6379
REDIS_DB=0
REDIS_SESSION_TTL=86400       # Session TTL in seconds (24 hours)
REDIS_MAX_MESSAGES=100        # Max messages per session (LRU eviction)

# Context Manager Configuration
CONTEXT_TTL_SECONDS=86400     # Student context TTL (24 hours)
MAX_CONTEXT_SESSIONS=1000     # Max concurrent sessions (LRU eviction)

# CORS Configuration
ALLOW_ALL_ORIGINS=false
ALLOWED_ORIGINS=http://localhost,http://localhost:80

# Streaming Configuration
STREAMING_DISABLED=false

# LangChain Debug Mode
LANGCHAIN_DEBUG=false

# Embedding Provider (google or local)
EMBEDDING_PROVIDER=google

# Frontend Configuration
VITE_BACKEND_URL=http://localhost:8000
```

### Database Schema

```sql
-- Programs: MSIT, MSBA, MSM
CREATE TABLE programs (
    id INTEGER PRIMARY KEY,
    program_code TEXT,
    program_name TEXT,
    total_credits INTEGER
);

-- Specialties: Data Science, Cybersecurity, etc.
CREATE TABLE specialties (
    id INTEGER PRIMARY KEY,
    specialty_name TEXT,
    program_id INTEGER REFERENCES programs(id)
);

-- Courses: MIS502, DS501, etc.
CREATE TABLE courses (
    id INTEGER PRIMARY KEY,
    course_code TEXT,
    course_name TEXT,
    credits REAL,
    is_core BOOLEAN
);

-- Many-to-many: specialty ↔ courses
CREATE TABLE specialty_courses (
    specialty_id INTEGER REFERENCES specialties(id),
    course_id INTEGER REFERENCES courses(id)
);
```

### Vector Database (ChromaDB)

The vector database provides semantic search capabilities and uses persistent storage.

**Initialization Behavior:**
- Uses `PersistentClient` - data is NOT regenerated on every startup
- Indexes only rebuild if collections are empty OR embedding dimensions change
- Location: `/app/database/vector_db` (Docker) or `database/vector_db` (local)

**Current Index:**
| Collection | Items | Description |
|------------|-------|-------------|
| courses | 89 | Course descriptions with embeddings |
| programs | 3 | MSIT, MSBA, MSM program details |
| specialties | 7 | Specialty focus areas |

**Embedding Providers:**
- `google` (default): 768 dimensions, requires GOOGLE_API_KEY
- `local`: 384 dimensions, uses sentence-transformers (no API required)

**Manual Rebuild:**
```python
# Rebuild all indexes (e.g., after course data updates)
from app.services.vector_search_service import VectorSearchService, EntityType
vector_service = VectorSearchService()
vector_service.rebuild_index(EntityType.ALL)
```

## Testing

```bash
# Backend tests
cd backend
source venv/bin/activate
pytest -v

# With coverage
pytest --cov=app --cov-report=html

# Specific test file
pytest tests/test_intent_agent_parser.py -v
```

## Troubleshooting

### Port Already in Use
```bash
lsof -ti :5173 | xargs kill -9  # Frontend
lsof -ti :8000 | xargs kill -9  # Backend
```

### API Key Issues
```bash
# Check .env exists
cat backend/.env | grep GOOGLE_API_KEY

# If missing, create from template
cp backend/.env.example backend/.env
# Edit and add your key
```

### Rate Limit Errors (429)
```
429 You exceeded your current quota
```
- Wait 60 seconds and retry
- Or upgrade to paid Gemini API plan

### Agent Format Errors
```
Invalid Format: Missing 'Action:' after 'Thought:
```
- This is auto-handled by the agent
- If persistent, check the prompt template in `adviser_agent.py`

## Technology Stack

| Component | Technology |
|-----------|------------|
| Frontend | React 19 + TypeScript + Vite |
| Styling | TailwindCSS |
| Web Server | Nginx (production) |
| Backend | FastAPI + Python 3.12 |
| LLM | Google Gemini 2.5 Flash/Pro |
| Agent Framework | LangChain |
| Database | SQLite |
| Vector Database | ChromaDB (semantic search) |
| Embeddings | Google Embeddings API or Sentence Transformers |
| Cache/Session | Redis 7 |
| Streaming | Server-Sent Events (SSE) |
| PDF Extraction | Gemini Vision API |
| Deployment | Docker + Docker Compose |

## License

MIT License - see LICENSE file for details.
