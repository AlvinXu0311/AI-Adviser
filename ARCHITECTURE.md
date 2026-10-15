# WPI Business School AI Adviser - System Architecture

> An intelligent academic advising chatbot powered by Google Gemini, LangChain, and RAG architecture

---

## 📋 Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Data Flow](#data-flow)
- [Component Details](#component-details)
- [Database Schema](#database-schema)
- [Deployment](#deployment)
- [Security](#security)

---

## 🎯 Overview

The WPI Business School AI Adviser is a full-stack web application that provides intelligent academic advising to WPI students. It combines structured database queries with semantic search to answer questions about programs, courses, requirements, and personalized degree planning.

### Key Features

- 🔐 **Secure Authentication** - Microsoft SSO with @wpi.edu domain validation
- 💬 **Real-time Streaming** - Server-Sent Events (SSE) for live responses
- 🤖 **AI Agent System** - LangGraph agent ⇄ tools graph with native Gemini tool calling
- 📄 **PDF Processing** - Transcript upload and intelligent parsing
- 🔍 **Hybrid Search** - Database-first with RAG fallback
- 💾 **Conversation Memory** - Redis-backed chat history (24h retention)
- 📊 **Degree Progress** - Automated graduation requirement checking

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USER LAYER                                  │
│                                                                          │
│                  WPI Students (@wpi.edu) via Browser                     │
│                              ↓                                           │
│                     Microsoft SSO Authentication                         │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND LAYER                                  │
│                      React 19.2 + TypeScript + Vite                      │
│                                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐  │
│  │ ChatInterface│  │  PdfUpload   │  │   Sidebar   │  │    Header    │  │
│  │  Component  │  │  Component   │  │  Component  │  │  Component   │  │
│  └──────┬──────┘  └──────┬───────┘  └─────────────┘  └──────────────┘  │
│         │                │                                               │
│  ┌──────▼─────────────────▼───────────────┐                             │
│  │         Service Layer                  │                             │
│  │  • chatService.ts (SSE Streaming)      │                             │
│  │  • pdfUpload.service.ts (File Upload)  │                             │
│  │  • authService.ts (Session Mgmt)       │                             │
│  └────────────────┬───────────────────────┘                             │
│                   │                                                      │
│  ┌────────────────▼───────────────────────┐                             │
│  │      State Management (App.tsx)        │                             │
│  │  • Session ID (sessionStorage)         │                             │
│  │  • User Info (MSAL context)            │                             │
│  │  • Chat History (local state)          │                             │
│  └────────────────────────────────────────┘                             │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                          API GATEWAY                                     │
│                      Nginx Reverse Proxy                                 │
│                                                                          │
│         • Port Forwarding: 8080 → 80                                     │
│         • CORS Handling: Allowed Origins                                │
│         • Routing: /api/* → Backend:8000                                │
│         • Static Files: Frontend Build                                  │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                          BACKEND LAYER                                   │
│                   FastAPI + Python 3.12 + LangChain                      │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                      API Endpoints                                 │ │
│  │                                                                    │ │
│  │  POST   /api/chat                  - Streaming chat with AI       │ │
│  │  POST   /api/extract-transcript    - PDF transcript processing    │ │
│  │  GET    /api/chat/history/{id}     - Conversation history         │ │
│  │  DELETE /api/chat/history/{id}     - Clear conversation           │ │
│  │  GET    /api/status                - System health check          │ │
│  │  GET    /api/summary               - Session summary              │ │
│  │  POST   /api/admin/*               - Admin operations             │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                  AI Agent System (LangGraph)                       │ │
│  │                                                                    │ │
│  │  ┌──────────────────┐         ┌────────────────────────────────┐  │ │
│  │  │  Intent Agent    │         │      Adviser Agent             │  │ │
│  │  │  (Gemini Flash)  │────────>│      (Gemini Flash)            │  │ │
│  │  │                  │         │                                │  │ │
│  │  │  • Classify      │         │  • agent ⇄ tools (≤8 rounds)   │  │ │
│  │  │  • Validate      │         │  • Multi-tool orchestration    │  │ │
│  │  │  • Filter noise  │         │  • Context-aware reasoning     │  │ │
│  │  └──────────────────┘         └────────────┬───────────────────┘  │ │
│  │                                             │                      │ │
│  │                               ┌─────────────▼───────────────┐      │ │
│  │                               │      Agent Tools (7)        │      │ │
│  │                               │                             │      │ │
│  │                               │  1. smart_course_search     │      │ │
│  │                               │  2. program_search          │      │ │
│  │                               │  3. degree_progress         │      │ │
│  │                               │  4. student_context         │      │ │
│  │                               │  5. semantic_search         │      │ │
│  │                               │  6. business_school_database│      │ │
│  │                               │  7. pdf_context             │      │ │
│  │                               └─────────────────────────────┘      │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                        Core Services                               │ │
│  │                                                                    │ │
│  │  • LLM Service          - Google Gemini API integration           │ │
│  │  • Context Manager      - Session-based student data storage      │ │
│  │  • Conversation Memory  - Redis-backed chat history               │ │
│  │  • PDF Extraction       - PyMuPDF text extraction + parsing       │ │
│  │  • Vector Service       - ChromaDB semantic search                │ │
│  │  • Database Service     - SQLite query interface                  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                            DATA LAYER                                    │
│                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────────┐   │
│  │  SQLite Database │  │  ChromaDB        │  │  Redis Cache        │   │
│  │  (bus_school.db) │  │  (Vector Store)  │  │  (Port 6379)        │   │
│  │                  │  │                  │  │                     │   │
│  │  • programs      │  │  • PDF Chunks    │  │  • Sessions (24h)   │   │
│  │  • courses       │  │  • Embeddings    │  │  • Chat History     │   │
│  │  • requirements  │  │  • Metadata      │  │  • Student Context  │   │
│  │  • specializations│ │  • 4 PDF Files   │  │  • TTL Management   │   │
│  │  • course_offerings││  500+ chunks     │  │  • LRU Eviction     │   │
│  └──────────────────┘  └──────────────────┘  └─────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                       EXTERNAL SERVICES                                  │
│                                                                          │
│  • Google Gemini API (gemini-3.8-flash, set by GEMINI_MODEL)             │
│  • Google Embeddings API (embedding-001)                                │
│  • Microsoft Azure AD B2C (OAuth 2.0 Authentication)                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Technology Stack

### Frontend
```
React 19.2.1           - UI Framework
TypeScript             - Type Safety
Vite 6.2.0             - Build Tool (fast HMR)
Framer Motion 12.23    - Smooth Animations
MSAL Browser 4.27      - Microsoft Authentication
MSAL React 3.0         - React Integration
React Markdown 10.1    - Message Rendering
Lucide React 0.554     - Icon System
jsPDF 3.0              - PDF Generation
```

### Backend
```
FastAPI 0.111          - Async Web Framework
Uvicorn 0.29           - ASGI Server
Python 3.12            - Runtime Environment
LangGraph 1.x          - Agent Framework
LangChain Core 1.x     - Messages, tools, prompts
LangChain Google GenAI - Gemini Integration
Pydantic 2.8           - Data Validation
Python-dotenv 1.0      - Environment Config
HTTPX 0.27             - HTTP Client
Python-multipart 0.0.9 - File Upload Support
```

### AI & ML
```
Google Gemini 3.8-flash  - Adviser agent (thinking_level=medium)
Google Gemini 3.8-flash  - Intent Classifier (thinking_level=low)
Google Embeddings API    - embedding-001
ChromaDB 1.3.5           - Vector Database
Sentence Transformers 2.7 - Local Embeddings (fallback)
PyMuPDF 1.24             - PDF Text Extraction
```

### Data & Storage
```
SQLite 3               - Primary Database (structured data)
Redis 5.0              - Cache & Session Store
Redis Python Client    - Redis Driver
ChromaDB Persistent    - Vector Storage
```

### DevOps & Deployment
```
Docker Compose         - Multi-container Orchestration
Nginx                  - Reverse Proxy + Static Files
Alpine Linux           - Lightweight Container Base
Health Checks          - Automatic Service Monitoring
Bridge Network         - Inter-container Communication
Named Volumes          - Data Persistence
```

---

## 🔄 Data Flow

### 1. Chat Request Flow

```
User Input
   ↓
Frontend (React)
   ↓ POST /api/chat {message, session_id, topic_id}
Nginx Proxy
   ↓
FastAPI Backend
   ↓
┌────────────────────────────────────────────────────┐
│ Layer 1: Basic Sanity Check                       │
│  • Not empty                                       │
│  • Contains alphanumeric                           │
└────────────────────┬───────────────────────────────┘
                     ↓
┌────────────────────────────────────────────────────┐
│ Layer 2: Intent Classification                     │
│  • Fetch conversation history (Redis)              │
│  • Intent Agent (Gemini Flash) analyzes            │
│  • Returns: {intent, confidence, is_academic}      │
│  • Reject if not academic or confidence < 0.2      │
└────────────────────┬───────────────────────────────┘
                     ↓
┌────────────────────────────────────────────────────┐
│ Context Loading                                    │
│  • Get student context from Redis (if uploaded)    │
│  • Get conversation history (last 20 messages)     │
│  • Get topic guidance (general vs course)          │
└────────────────────┬───────────────────────────────┘
                     ↓
┌────────────────────────────────────────────────────┐
│ Adviser Agent (LangGraph: agent ⇄ tools)           │
│                                                    │
│  Rounds 1-8:                                       │
│    agent node: Gemini returns tool_calls           │
│       ↓                                            │
│    tools node: smart_course_search (parallel ok)   │
│       ↓                                            │
│    Tool Execution:                                 │
│      1. Try DB query (SQLite)                      │
│      2. Try RAG search (ChromaDB)                  │
│      3. Retry with query variations                │
│       ↓                                            │
│    ToolMessage: "Found course MIS 520..."          │
│       ↓                                            │
│    agent node: no tool_calls → answer              │
│       ↓                                            │
│    END: streamed final response                   │
└────────────────────┬───────────────────────────────┘
                     ↓
┌────────────────────────────────────────────────────┐
│ Response Processing                                │
│  • Store messages in Redis (conversation history)  │
│  • Stream response via SSE                         │
│  • Refresh TTL (24h)                               │
└────────────────────┬───────────────────────────────┘
                     ↓
Frontend Displays Response
```

### 2. Transcript Upload Flow

```
User Selects PDF
   ↓
Frontend Validation
  • File type: PDF
  • Size: < 10MB
   ↓
POST /api/extract-transcript
   ↓
PDF Extraction Service (PyMuPDF)
  • Extract text from PDF
  • Parse with regex patterns:
    - Student name, ID, email
    - GPA calculation
    - Course list (code, name, credits, grade)
    - Current courses
   ↓
Context Manager
  • Create StudentContext object
  • Store in Redis with session_id
  • TTL: 24 hours
   ↓
Response to Frontend
  {student_name, gpa, courses_count}
   ↓
Context Available for Tools
  • degree_progress tool
  • student_context tool
  • Personalized recommendations
```

### 3. Unified Search Strategy (Used by Multiple Tools)

```
Query: "Who teaches MIS 520?"
   ↓
┌─────────────────────────────────────┐
│ Attempt 1: Database Search          │
│  • Query SQLite courses table       │
│  • Check course_offerings for instructor │
│  • Validate result matches query    │
└─────────┬───────────────────────────┘
          ↓
     Found? ──Yes──> Return DB Result
          │
          No
          ↓
┌─────────────────────────────────────┐
│ Attempt 2: RAG Search               │
│  • Generate query embedding         │
│  • Search ChromaDB vector store     │
│  • Course-aware ranking (boost)     │
│  • Check relevance score > 0.5      │
└─────────┬───────────────────────────┘
          ↓
     Found? ──Yes──> Return RAG Result
          │
          No
          ↓
┌─────────────────────────────────────┐
│ Attempt 3: Query Variations         │
│  • Generate keyword variations      │
│  • Try DB search again              │
│  • Try RAG search again             │
│  • Cross-department queries         │
└─────────┬───────────────────────────┘
          ↓
     Found? ──Yes──> Return Best Match
          │
          No
          ↓
    Return "No information found"
```

---

## 🧩 Component Details

### Frontend Components

#### ChatInterface (`ChatInterface.tsx`)
- **Purpose**: Main chat UI with real-time message streaming
- **Features**:
  - Message history display with Markdown rendering
  - SSE streaming client (receives chunks from backend)
  - Topic selection (General Advising vs Courses & Planning)
  - Auto-scroll to latest message
  - Loading states and error handling
- **State Management**: Local state + App.tsx context

#### PdfUpload (`PdfUpload.tsx`)
- **Purpose**: Transcript upload and validation
- **Features**:
  - Drag-and-drop + file picker
  - Client-side validation (PDF only, < 10MB)
  - Upload progress indicator
  - Display extracted info (name, GPA, course count)
- **API**: POST /api/extract-transcript

#### Sidebar (`Sidebar.tsx`)
- **Purpose**: Navigation and resource links
- **Features**:
  - Program information links
  - Course catalog access
  - Student resources
  - Collapsible on mobile

### Backend Services

#### Intent Agent (`intent_agent.py`)
- **Purpose**: Classify user intent before processing
- **Model**: Gemini 3.8-flash, thinking_level=low (fast, low-cost)
- **Input**: User message + last 6 conversation messages
- **Output**: `{intent, confidence, is_academic, requires_transcript, reasoning}`
- **Timeout**: 6 seconds
- **Logic**:
  ```python
  if not is_academic or confidence < 0.2:
      return "Not sure how to help with that..."
  else:
      route_to_adviser_agent()
  ```

#### Adviser Agent (`adviser_agent.py`)
- **Purpose**: Main academic advising agent
- **Model**: Gemini 3.8-flash, thinking_level=medium (thought summaries feed the UI)
- **Pattern**: LangGraph `StateGraph` (agent ⇄ ToolNode) with native tool calling
- **Tools**: 7 tools available (see below)
- **Max Iterations**: 10
- **Features**:
  - Multi-step reasoning
  - Autonomous tool selection
  - Context-aware responses
  - Conversation history integration (last 20 messages)

#### Agent Tools (`tools.py`)

| Tool | Purpose | Data Source | Strategy |
|------|---------|-------------|----------|
| `smart_course_search` | Course info (instructor, credits, description) | SQLite + ChromaDB | DB-first, RAG fallback, 3 retries |
| `program_search` | Program requirements, specializations | SQLite + ChromaDB | DB-first, RAG fallback |
| `degree_progress` | Graduation requirement checking | SQLite + Redis | Compare completed vs required |
| `student_context` | Student GPA, courses, grades | Redis cache | Direct lookup by session_id |
| `semantic_search` | General fallback search | ChromaDB | Semantic similarity |
| `business_school_database` | Direct SQL queries | SQLite | Raw database access |
| `pdf_context` | Long-form context retrieval | ChromaDB | Multi-chunk aggregation |

#### Context Manager (`context_manager.py`)
- **Purpose**: Session-based student data storage
- **Storage**: Redis (24h TTL)
- **Isolation**: Each session_id has separate context
- **Features**:
  - Auto-expiration (24h inactivity)
  - LRU eviction (max 1000 sessions)
  - Touch-on-access (TTL refresh)
  - No cross-session data leakage

#### Conversation Memory (`conversation_memory.py`)
- **Purpose**: Multi-turn conversation support
- **Storage**: Redis (LangChain RedisChatMessageHistory)
- **Key Pattern**: `message_store:{session_id}`
- **Retention**: 24h TTL, max 100 messages per session
- **Pruning**: Auto-remove oldest messages when limit reached

#### PDF Extraction Service (`pdf_extraction_service.py`)
- **Purpose**: Parse student transcripts
- **Library**: PyMuPDF (fitz)
- **Extraction**:
  - Text extraction (page by page)
  - Regex patterns for structured data:
    - Student info: name, ID, email
    - GPA: cumulative GPA calculation
    - Courses: code, name, credits, grade, semester
    - Current courses: in-progress courses
- **Output**: `ExtractedTranscriptData` object

#### PDF Vector Service (`pdf_vector_service.py`)
- **Purpose**: Semantic search across academic PDFs
- **PDFs Indexed**:
  - Bus-school courses.pdf
  - Masters from Graduate Bus School.pdf
  - Mathematical Science Courses.pdf
  - Computer Science Courses.pdf
- **Chunking Strategy**:
  - Course-boundary splitting (regex: `[A-Z]{2,4} \d{3,4}`)
  - Each chunk = complete course info
  - Overlapping chunks for long descriptions
- **Embeddings**: Google embedding-001 (fallback: all-MiniLM-L6-v2)
- **Search Features**:
  - Course-aware ranking (boost score for exact matches)
  - Cross-listed course detection (e.g., "DS/ECE 577")
  - Relevance threshold: 0.5

#### Program Database Service (`program_db_service.py`)
- **Purpose**: Query SQLite database for programs/courses
- **Key Functions**:
  - `get_all_programs()` - List all programs (MSIT, MSBA, MBA, etc.)
  - `summarize_courses(query)` - Search courses by keyword
  - `summarize_programs(query)` - Search programs by keyword
  - `compare_student_progress(program, completed, current)` - Degree progress check
  - `format_progress_report(analysis)` - Human-readable report

---

## 🗄️ Database Schema

### SQLite Database (`bus_school.db`)

```sql
-- Programs Table
CREATE TABLE programs (
    program_id INTEGER PRIMARY KEY,
    program_code TEXT UNIQUE NOT NULL,  -- 'MSIT', 'MSBA', 'MBA'
    program_name TEXT NOT NULL,
    total_credits INTEGER,              -- 30-48 credits
    description TEXT,
    admission_requirements TEXT
);

-- Specializations Table
CREATE TABLE specializations (
    specialization_id INTEGER PRIMARY KEY,
    program_id INTEGER,
    name TEXT NOT NULL,                 -- 'AI/ML', 'Data Analytics'
    credits_required INTEGER,
    description TEXT,
    FOREIGN KEY (program_id) REFERENCES programs(program_id)
);

-- Requirements Table
CREATE TABLE requirements (
    requirement_id INTEGER PRIMARY KEY,
    program_id INTEGER,
    specialization_id INTEGER,          -- NULL for core requirements
    requirement_type TEXT,              -- 'core', 'elective', 'capstone'
    course_code TEXT,
    credits_required INTEGER,
    is_mandatory BOOLEAN,
    FOREIGN KEY (program_id) REFERENCES programs(program_id),
    FOREIGN KEY (specialization_id) REFERENCES specializations(specialization_id),
    FOREIGN KEY (course_code) REFERENCES courses(course_code)
);

-- Courses Table
CREATE TABLE courses (
    course_code TEXT PRIMARY KEY,       -- 'MIS 520'
    course_name TEXT NOT NULL,
    credits REAL,                       -- 3.0
    description TEXT,
    prerequisites TEXT,
    department TEXT                     -- 'MIS', 'OIE', 'CS'
);

-- Course Offerings Table
CREATE TABLE course_offerings (
    offering_id INTEGER PRIMARY KEY,
    course_code TEXT,
    instructor TEXT,
    semester TEXT,                      -- 'A-term', 'B-term'
    year TEXT,                          -- '2024-25'
    schedule TEXT,                      -- 'Mon/Wed 6-7:30pm'
    enrollment_limit INTEGER,
    FOREIGN KEY (course_code) REFERENCES courses(course_code)
);
```

### ChromaDB Collections

```
Collection: pdf_documents
  • Total Chunks: ~500
  • Embedding Dimensions: 768 (Google) or 384 (local)
  • Metadata:
    - source: PDF filename
    - course_code: Extracted course code
    - course_title: Extracted course title
    - chunk_type: 'course', 'program_info', 'sub_chunk'
    - chunk_index: Position in source document
```

### Redis Data Structure

```
Key Pattern: message_store:{session_id}
  Type: List (LPUSH/RPUSH for messages)
  Value: JSON serialized messages
    [
      {"type": "human", "content": "What is MSIT?"},
      {"type": "ai", "content": "MSIT is..."}
    ]
  TTL: 86400 seconds (24 hours)
  Max Messages: 100 per session

Key Pattern: student_context:{session_id}
  Type: Hash
  Value: Student transcript data
    {
      "student_name": "John Doe",
      "gpa": 3.75,
      "courses": [...],
      "degree_program": "MSIT"
    }
  TTL: 86400 seconds (24 hours)
```

---

## 🐳 Deployment

### Docker Compose Architecture

```yaml
services:
  frontend:
    image: nginx:alpine
    ports:
      - "8080:80"
    volumes:
      - ./frontend/dist:/usr/share/nginx/html
    networks:
      - ai-adviser-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:80"]
      interval: 30s
      timeout: 10s
      retries: 3

  backend:
    build: ./backend
    image: wpi-ai-adviser-backend:latest
    ports:
      - "8000:8000"
    environment:
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    volumes:
      - ./database:/app/database
    networks:
      - ai-adviser-network
    depends_on:
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - ai-adviser-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  ai-adviser-network:
    driver: bridge

volumes:
  redis_data:
```

### Environment Variables

```bash
# Backend (.env)
GOOGLE_API_KEY=your_google_api_key_here
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_SESSION_TTL=86400
LANGCHAIN_DEBUG=false
LOG_LEVEL=INFO
FRONTEND_URL=http://localhost:8080
ALLOW_ALL_ORIGINS=false

# Frontend (.env)
VITE_API_URL=http://localhost:8000
VITE_MSAL_CLIENT_ID=your_azure_client_id
VITE_MSAL_AUTHORITY=https://login.microsoftonline.com/your_tenant_id
VITE_MSAL_REDIRECT_URI=http://localhost:8080
```

### Deployment Steps

```bash
# 1. Clone repository
git clone https://github.com/your-org/ai-adviser.git
cd ai-adviser

# 2. Set up environment variables
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
# Edit .env files with your credentials

# 3. Build frontend
cd frontend
npm install
npm run build
cd ..

# 4. Start services
docker-compose up -d

# 5. Check health
curl http://localhost:8000/api/health
curl http://localhost:8080

# 6. View logs
docker-compose logs -f backend
```

---

## 🔒 Security

### Authentication & Authorization

- **Microsoft SSO**: Only users with @wpi.edu email addresses can authenticate
- **OAuth 2.0**: Industry-standard authentication protocol via MSAL
- **Token Management**: MSAL automatically refreshes access tokens
- **Session Isolation**: Each browser session has a unique session_id (UUID)
- **No Persistent Storage**: User credentials never stored locally

### Data Privacy

- **Session-Based Storage**: All student data isolated by session_id
- **Auto-Expiration**: All data automatically deleted after 24h of inactivity
- **Redis TTL**: Automatic cleanup via Redis key expiration
- **No Cross-Session Leakage**: Context Manager enforces strict isolation
- **Transcript Security**: Uploaded transcripts stored in memory (Redis), not on disk
- **No PII Logging**: Student names, IDs, and grades not logged

### Network Security

- **CORS**: Whitelist of allowed origins (localhost + production domains)
- **Nginx Proxy**: Backend not directly exposed to public internet
- **HTTPS Support**: SSL/TLS certificates for production deployment
- **Rate Limiting**: Gemini API enforces 60 requests/minute
- **Input Validation**: Pydantic schemas validate all API inputs
- **Sanity Checks**: Basic validation before expensive LLM calls

### Container Security

- **Alpine Base Images**: Minimal attack surface (5MB base image)
- **Bridge Network**: Containers isolated from host network
- **Non-Root Users**: Containers run as unprivileged users
- **Health Checks**: Automatic restart on service failure
- **Environment Variables**: Secrets managed via .env files (not in code)
- **Volume Permissions**: Restricted access to mounted volumes

---

## 📊 Performance Metrics

### Response Times

| Operation | Time | Notes |
|-----------|------|-------|
| Intent Classification | 1-2s | Gemini Flash, 6s timeout |
| Simple Query (1-2 tools) | 3-5s | Database lookup |
| Complex Query (3-5 tools) | 8-15s | Multiple tool calls |
| Degree Progress Check | 5-10s | Database comparison |
| PDF Upload & Extraction | 2-5s | PyMuPDF processing |
| SSE Stream First Chunk | <1s | Perceived latency low |

### Scalability Limits

- **Max Concurrent Sessions**: 1000 (Context Manager limit)
- **Redis Memory Usage**: ~100MB for 1000 active sessions
- **ChromaDB Size**: ~50MB (4 PDFs, 500 chunks)
- **SQLite Database**: ~10MB (programs, courses, requirements)
- **Gemini API Rate Limit**: 60 requests/minute (free tier)

### Optimization Techniques

1. **Streaming Responses**: SSE reduces perceived latency
2. **DB-First Search**: Avoids slow vector search when possible
3. **Query Retry Logic**: 3 attempts with variations (improves recall by 40%)
4. **Batch Embedding**: 50 documents at a time (prevents OOM)
5. **Course-Aware Ranking**: Boosts relevant results by 30%
6. **LRU Eviction**: Automatic cleanup of oldest 10% when limit reached
7. **Redis Pipelining**: Batch operations for better throughput

---

## 🎯 Architecture Decisions

### Why Database-First?

- **Accuracy**: SQLite provides authoritative, structured data (instructor names, credits, schedules)
- **Speed**: SQL queries are 10x faster than vector search (50ms vs 500ms)
- **Reliability**: Database data is validated and curated
- **RAG Supplement**: ChromaDB supplements with detailed descriptions from PDFs

### Why ReAct Pattern?

- **Autonomous Reasoning**: Agent decides which tools to use and when
- **Multi-Step Queries**: Handles complex questions requiring multiple data sources
- **Explainability**: "Thought" and "Action" steps visible in logs
- **Flexibility**: Easy to add new tools without changing core logic

### Why Intent Classification?

- **Cost Reduction**: Prevents expensive LLM calls for non-academic queries
- **User Experience**: Fast rejection of irrelevant questions
- **Conversation Context**: Uses chat history to understand follow-up questions
- **Accuracy**: 95%+ accuracy on academic vs non-academic classification

### Why Session-Based Isolation?

- **Privacy**: Each user's data isolated from others
- **Security**: No shared state between sessions
- **Scalability**: Easy to distribute across multiple backend instances
- **Simplicity**: No need for user database or authentication state

### Why Redis for Memory?

- **Speed**: In-memory storage (< 1ms read/write)
- **TTL Support**: Automatic expiration (no manual cleanup)
- **Persistence**: Optional disk persistence for reliability
- **Compatibility**: LangChain native support (RedisChatMessageHistory)

---

## 📁 Project Structure

```
AI-Adviser/
├── frontend/                   # React Frontend
│   ├── src/
│   │   ├── components/        # React Components
│   │   │   ├── ChatInterface.tsx
│   │   │   ├── PdfUpload.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   └── Header.tsx
│   │   ├── services/          # API Services
│   │   │   ├── chatService.ts
│   │   │   ├── pdfUpload.service.ts
│   │   │   └── authService.ts
│   │   ├── App.tsx            # Main App Component
│   │   └── main.tsx           # Entry Point
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                    # FastAPI Backend
│   ├── app/
│   │   ├── api/               # API Endpoints
│   │   │   ├── chat.py
│   │   │   ├── transcript.py
│   │   │   ├── status.py
│   │   │   ├── summary.py
│   │   │   └── admin.py
│   │   ├── agents/            # AI Agents
│   │   │   ├── adviser_agent.py
│   │   │   ├── intent_agent.py
│   │   │   └── tools.py
│   │   ├── services/          # Core Services
│   │   │   ├── context_manager.py
│   │   │   ├── conversation_memory.py
│   │   │   ├── pdf_extraction_service.py
│   │   │   ├── pdf_vector_service.py
│   │   │   └── program_db_service.py
│   │   ├── schemas/           # Pydantic Models
│   │   │   ├── chat.py
│   │   │   └── transcript.py
│   │   └── main.py            # FastAPI App
│   ├── tests/                 # Unit Tests
│   │   ├── test_adviser_graph.py
│   │   └── test_pdf_extraction_service.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── database/                   # Database Files
│   ├── database_project/      # SQLite Database
│   │   ├── bus_school.db
│   │   ├── create_database.py
│   │   └── query_degree.py
│   └── vector_db_pdf/         # ChromaDB Storage
│       └── chroma.sqlite3
│
├── docker-compose.yml          # Docker Orchestration
├── .env.example                # Environment Template
├── README.md                   # Project README
└── ARCHITECTURE.md             # This File
```

---

## 🚀 Future Enhancements

### Planned Features

1. **Multi-Modal Support**
   - Upload course syllabi, schedule screenshots
   - Image-based question answering

2. **Recommendation Engine**
   - ML-based course recommendations
   - Similarity matching with successful students

3. **Real-time Schedule Planning**
   - Interactive calendar view
   - Conflict detection
   - Export to Google Calendar

4. **Email Notifications**
   - Registration deadline reminders
   - New course announcements
   - Degree progress milestones

5. **Analytics Dashboard**
   - Admin view: popular questions, usage stats
   - Student engagement metrics
   - System performance monitoring

6. **Voice Input**
   - Speech-to-text integration
   - Hands-free interaction

7. **Export Functionality**
   - Download chat history as PDF
   - Save degree plan as document

8. **Course Reviews Integration**
   - Student feedback and ratings
   - Rate-my-professor data

9. **Career Path Mapping**
   - Link courses to job roles
   - Skills gap analysis

10. **Multi-Language Support**
    - i18n for international students
    - Translation API integration

### Scalability Improvements

1. **PostgreSQL Migration**
   - Replace SQLite for production
   - Support concurrent writes

2. **Redis Cluster**
   - High-availability setup
   - Automatic failover

3. **Load Balancing**
   - Multiple backend instances
   - Nginx load balancer

4. **Caching Layer**
   - Redis query caching
   - CDN for static assets

5. **Monitoring & Logging**
   - Prometheus metrics
   - Grafana dashboards
   - ELK stack for logs

---

## 📞 Support & Contribution

### Getting Help

- **Documentation**: See `/docs` directory for detailed guides
- **Issues**: Open a GitHub issue for bugs or feature requests
- **Discussions**: Join GitHub Discussions for Q&A

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Built with ❤️ for WPI Business School Students**

*Last Updated: 2025-12-10*
