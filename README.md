# WPI Business School Digital Adviser

Interactive chatbot platform for academic advising with PDF transcript upload, **LangChain ReAct agents**, and **Database-First architecture**.

## Key Features

| Feature | Technology | Description |
|---------|------------|-------------|
| **ReAct Agent Framework** | LangChain + Gemini 2.5 Pro | Multi-step reasoning with Thought → Action → Observation loops |
| **Database-First Architecture** | SQLite + ChromaDB | Authoritative SQL queries with semantic search fallback |
| **Unified Search Layer** | Custom Tool Chain | DB-first → RAG fallback → Smart retry with query variations |
| **Real-time Streaming** | SSE + FastAPI | Token-by-token response with live tool call visualization |
| **PDF Transcript Extraction** | Gemini Vision API | OCR + structured data extraction from academic transcripts |
| **Session Isolation** | Redis + Context Managers | Per-session memory with TTL expiration and LRU eviction |
| **Conversational AI** | Prompt Engineering | Asks clarifying questions before making assumptions |

## Architecture Highlights

### ReAct (Reasoning + Acting) Framework

The core of the Digital Adviser is a **LangChain ReAct agent** that performs multi-step reasoning:

```
┌─────────────────────────────────────────────────────────────────┐
│                    ReAct Agent Loop                              │
│                                                                  │
│   User Query                                                     │
│       ↓                                                         │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ Thought: "I need to find MSIT specialization info..."   │   │
│   │ Action: program_search                                   │   │
│   │ Action Input: "MSIT specializations"                     │   │
│   └─────────────────────────────────────────────────────────┘   │
│       ↓                                                         │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ Observation: "MSIT offers AI, Systems Design, ..."      │   │
│   └─────────────────────────────────────────────────────────┘   │
│       ↓                                                         │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ Thought: "Now I need course details for each..."        │   │
│   │ Action: smart_course_search                              │   │
│   │ Action Input: "MIS 587 Predictive Analytics"             │   │
│   └─────────────────────────────────────────────────────────┘   │
│       ↓                                                         │
│   ... (2-9 tool calls for complex questions) ...                │
│       ↓                                                         │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ Thought: "I have enough information to answer."          │   │
│   │ Final Answer: [Complete, well-organized response]        │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Agent Tools

| Tool | Purpose | Architecture |
|------|---------|--------------|
| `smart_course_search` | Course details (instructor, credits, prerequisites) | Unified Search: DB → RAG → Retry |
| `program_search` | Program requirements and specializations | Unified Search: DB → RAG → Retry |
| `semantic_search` | General semantic search on PDF catalogs | ChromaDB with course-aware chunking |
| `degree_progress` | Student progress vs. program requirements | Requires uploaded transcript |
| `student_context` | Access student's uploaded transcript data | Session-scoped with Redis |
| `business_school_database` | Direct SQL queries | SQLite (authoritative source) |

### Unified Search Strategy

```
Query → DB Search (SQLite) → Found? → Return
                ↓ No
        RAG Search (ChromaDB) → Found? → Return  
                ↓ No
        Retry with query variations (2-3 attempts)
                ↓ Still No
        Return "Not found" message
```

**Key Innovations:**
- **Course Code Validation**: Prevents false positives (e.g., "MA 571" won't return "MIS 571")
- **Score Boosting**: Exact course code matches get +0.5 relevance boost
- **Smart Retry**: Query variations (e.g., "MA 571" → "Financial Mathematics")

### MCP Server & Agent Skills

The same retrieval layer the ReAct agent uses (`backend/app/services/search_service.py`)
is also published as a [Model Context Protocol](https://modelcontextprotocol.io) server,
so any MCP client (Claude Code, Claude Desktop, Cursor, Dify) can query WPI program data.

| MCP tool | Purpose |
|------|---------|
| `search_courses` | Course lookup by code, topic, or instructor (DB → PDF catalog) |
| `get_course` | Structured database record for one course code |
| `search_programs` | Program requirements and specialties (DB → PDF catalog) |
| `get_program_structure` | Required / optional specialties and their courses |
| `check_degree_progress` | Audit a list of course codes against a program — stateless, no session needed |
| `search_catalog` / `get_catalog_context` | Semantic search over the PDF catalogs |

Resource: `adviser://programs` lists every program in the database. All tools are read-only.

Two **Agent Skills** in `.claude/skills/` package multi-step advising workflows on top of these tools:

- **`graduation-audit`** — resolve the program, normalize course codes, run the audit,
  look up every missing course, self-check that every claim came from a tool, and
  report in a fixed table format.
- **`course-planning`** — audit first, choose optional specialties, gather prerequisites
  and offering periods, schedule term by term, then verify the plan (prerequisite order,
  no invented or duplicate courses, all requirements covered) before answering.

Open the repo in Claude Code and both are picked up automatically (`.mcp.json` +
`.claude/skills/`). To run the server yourself:

```bash
cd backend
pip install -r mcp_server/requirements.txt   # separate from requirements.txt: mcp 2.x needs a newer starlette
python -m mcp_server.server                                         # stdio
python -m mcp_server.server --transport streamable-http --port 8765  # http://127.0.0.1:8765/mcp
```

## Tech Stack

### Frontend
| Technology | Purpose |
|------------|---------|
| **React 18** | Component-based UI with hooks |
| **TypeScript** | Type-safe development |
| **Vite** | Fast build tooling and HMR |
| **Tailwind CSS** | Utility-first styling |
| **Framer Motion** | Smooth animations |
| **Lucide React** | Modern icon library |
| **React Markdown + remark-gfm** | Rich markdown rendering with table support |
| **Nginx** | Production static file serving and reverse proxy |

### Backend
| Technology | Purpose |
|------------|---------|
| **FastAPI** | High-performance async API framework |
| **LangChain** | ReAct agent framework with tool orchestration |
| **Google Gemini 2.5 Pro** | LLM for reasoning and generation |
| **Gemini Vision API** | PDF transcript OCR and extraction |
| **ChromaDB** | Vector database for semantic search |
| **SQLite** | Structured program/course database |
| **Redis** | Session memory and conversation history |
| **Pydantic** | Data validation and serialization |
| **SSE (Server-Sent Events)** | Real-time streaming responses |

### DevOps
| Technology | Purpose |
|------------|---------|
| **Docker** | Containerized deployment |
| **Docker Compose** | Multi-service orchestration |
| **Cloudflare Tunnel** | Secure public access (optional) |

### AI/ML Architecture
| Component | Technology | Description |
|-----------|------------|-------------|
| **ReAct Agent** | LangChain + Gemini | Multi-step reasoning with tool use |
| **Intent Classification** | Free-form LLM | No hardcoded categories, natural language analysis |
| **Unified Search** | SQLite + ChromaDB | DB-first with semantic fallback |
| **Course-Aware Chunking** | Custom Regex | 272 course chunks with metadata |
| **Conversation Memory** | Redis + TTL | 24-hour session persistence |

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
│  - Real-time agent process visualization (tool calls, reasoning) │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Backend (FastAPI)                            │
│                                                                  │
│  ┌─────────────────┐    ┌──────────────────────────────────┐   │
│  │  Intent Agent   │───▶│       Adviser Agent (ReAct)       │   │
│  │  (Free-form LLM │    │  Multi-step reasoning with tools  │   │
│  │   Classification)    │  - smart_course_search            │   │
│  └─────────────────┘    │  - program_search                 │   │
│                         │  - semantic_search                │   │
│                         │  - degree_progress                │   │
│                         │  - student_context                │   │
│                         └──────────────────────────────────┘   │
│                                      │                          │
│                         ┌────────────┴────────────┐            │
│                         ▼                         ▼            │
│         ┌──────────────────┐    ┌─────────────────────┐        │
│         │ SQLite Database  │    │ ChromaDB Vector DB  │        │
│         │ (bus_school.db)  │    │  (PDF Catalog RAG)  │        │
│         │  - Programs (3)  │    │  - 272 course chunks│        │
│         │  - Specialties   │    │  - Course-aware     │        │
│         │  - Courses (103) │    │    chunking         │        │
│         └──────────────────┘    └─────────────────────┘        │
│                         │                                       │
│                         ▼                                       │
│              ┌──────────────────────┐                          │
│              │   Unified Search     │                          │
│              │  DB-first → RAG      │                          │
│              │  with retry logic    │                          │
│              └──────────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │      Redis       │
                    │ (Session Memory) │
                    └──────────────────┘
```

### Unified Search Architecture

All search tools share a common search strategy:

```
Query → DB Search (SQLite) → Found? → Return
                ↓ No
        RAG Search (ChromaDB) → Found? → Return
                ↓ No
        Retry with query variations (2-3 attempts)
                ↓ Still No
        Return "Not found" message
```

**Key Features:**
- **DB-First**: Structured SQL queries for accurate results
- **RAG Fallback**: Semantic search on PDF catalogs when DB fails
- **Smart Retry**: Query variations (e.g., "MA 571" → "MA" + "571" → "Financial Mathematics")
- **Course Code Validation**: Prevents false positives (e.g., "MA 571" won't return "MIS 571")
- **Score Boosting**: Exact course code matches get higher relevance scores

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
│   │   │   ├── adviser_agent.py      # ReAct agent with multi-step reasoning
│   │   │   ├── intent_agent.py       # Intent classification
│   │   │   ├── tools.py              # Unified search tools (smart_course_search, program_search, etc.)
│   │   │   └── streaming_callback.py # SSE streaming handler
│   │   ├── api/
│   │   │   ├── chat.py               # /api/chat endpoint (streaming)
│   │   │   ├── transcript.py         # /api/extract-transcript
│   │   │   └── status.py             # /api/status (system health)
│   │   ├── services/
│   │   │   ├── program_db_service.py # SQLite database queries
│   │   │   ├── pdf_vector_service.py  # ChromaDB with course-aware chunking
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
- **Agent process visualization** - See tool calls and reasoning steps in real-time
- **Multi-step reasoning display** - Watch the agent think through complex queries
- **Voice input** - Speech-to-text for questions
- **File upload** - PDF transcript extraction with Gemini Vision

### Intent Classification (Layer 1)
- **Free-form LLM analysis** - No hardcoded intent types
- **Confidence scoring** - 0.0-1.0 scale
- **Academic detection** - Filters non-academic queries
- **Transcript awareness** - Detects personal progress questions

### Adviser Agent (Layer 2)
- **ReAct pattern** - Thought → Action → Observation loop
- **Multi-step reasoning** - Complex questions trigger 2-9 tool calls
- **Unified Search** - DB-first with RAG fallback and retry logic
- **Tool use** - Automatic tool invocation based on query type
- **Agent process streaming** - Real-time visualization of tool calls

### Agent Tools

| Tool | Purpose | Example Queries |
|------|---------|-----------------|
| `smart_course_search` | Search for course details (instructor, credits, prerequisites) | "Who teaches MIS 587?", "What is CS 534 about?" |
| `program_search` | Search for program requirements and specializations | "What are MSIT requirements?", "MBA specializations" |
| `semantic_search` | General semantic search on PDF catalogs | "Machine learning courses", "AI curriculum" |
| `degree_progress` | Compare student progress against program requirements | "What courses do I still need for MBA?" |
| `student_context` | Access uploaded transcript data | "What's my GPA?", "What courses have I taken?" |
| `business_school_database` | Direct database queries | "List all programs" |
| `assess_complexity` | Analyze query complexity for routing | Internal routing decisions |

### Multi-Step ReAct Reasoning

For complex questions, the agent uses **multiple tools** in sequence:

**Example: "Create a study plan for MBA with Business Analytics focus"**
```
Step 1: program_search("MBA Business Analytics") → Get program requirements
Step 2: smart_course_search("MIS 502") → Get course details
Step 3: smart_course_search("MIS 584") → Get more course details
Step 4: smart_course_search("OIE 552") → Get analytics course info
...
Final Answer: Comprehensive study plan with all course descriptions
```

**Example: "Compare MSIT and MSBA for data analytics"**
```
Step 1: program_search("MSIT requirements") → Get MSIT info
Step 2: program_search("MSBA requirements") → Get MSBA info
Step 3: smart_course_search("data analytics courses") → Find relevant courses
Final Answer: Detailed comparison with recommendations
```

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
-- Programs: MSIT, MSBA, MBA, FinTech, MSOS
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

The vector database provides semantic search capabilities with **course-aware chunking**.

**Course-Aware Chunking:**
- Automatically detects course boundaries in PDF catalogs
- Each course becomes its own chunk with metadata (course_code, course_title)
- Supports cross-listed courses (e.g., "DS/ECE 577" detected as both)
- Result: 272 course chunks (vs. 81 with fixed-size chunking)

**Score Boosting:**
- Exact course code match: +0.5 relevance boost
- Course number match: +0.3 relevance boost
- Example: Query "ECE 577" → "ECE 577: Machine Learning in Cybersecurity" scores 1.00

**Initialization Behavior:**
- Uses `PersistentClient` - data is NOT regenerated on every startup
- Indexes only rebuild if collections are empty OR embedding dimensions change
- Location: `/app/database/vector_db` (Docker) or `database/vector_db` (local)

**Current Index:**
| Collection | Items | Description |
|------------|-------|-------------|
| pdf_chunks | 272 | Course-aware chunks from PDF catalogs |
| courses | 89 | Course descriptions with embeddings |
| programs | 6 | MSIT, MSBA, MBA, FinTech, MSOS program details |
| specialties | 7 | Specialty focus areas |

**PDF Sources Indexed:**
- Business School Courses (79 courses)
- Mathematical Science Courses (57 courses)
- Computer Science Courses (117 courses)

**Embedding Providers:**
- `google` (default): 768 dimensions, requires GOOGLE_API_KEY
- `local`: 384 dimensions, uses sentence-transformers (no API required)

**Manual Rebuild:**
```bash
# Rebuild PDF vector index via API
curl -X POST http://localhost:8000/api/admin/rebuild-pdf-index

# Or use the admin endpoint in browser
# GET http://localhost:8000/api/admin/pdf-index-stats
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
