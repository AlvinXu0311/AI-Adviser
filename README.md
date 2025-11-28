# WPI Business School Digital Adviser

Interactive chatbot platform for academic advising with PDF transcript upload, LangChain agents, and Database-First architecture.

## Quick Start

### Prerequisites

- Node.js 16+ (for frontend)
- Python 3.8+ (for backend)
- Google Gemini API key

### Automatic Start (Recommended)

```bash
# Change to project directory
cd AI-Adviser

# Make scripts executable (first time only)
chmod +x start.sh stop.sh

# Start both services (backend + frontend)
./start.sh

# Stop both services when done
./stop.sh
```

### Manual Start

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

### Access the Application

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                          │
│  - Chat Interface with streaming responses                       │
│  - PDF transcript upload with Gemini Vision extraction           │
│  - Real-time agent status indicators                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Backend (FastAPI)                            │
│                                                                  │
│  ┌─────────────────┐    ┌──────────────────────────────────┐   │
│  │  Intent Agent   │───▶│       Adviser Agent (ReAct)       │   │
│  │  (Free-form LLM │    │  - business_school_database tool  │   │
│  │   Classification)    │  - student_context tool           │   │
│  └─────────────────┘    │  - assess_complexity tool         │   │
│                         └──────────────────────────────────┘   │
│                                      │                          │
│                                      ▼                          │
│                         ┌──────────────────────┐                │
│                         │   SQLite Database    │                │
│                         │   (bus_school.db)    │                │
│                         │  - Programs (3)      │                │
│                         │  - Specialties (7)   │                │
│                         │  - Courses (14)      │                │
│                         └──────────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
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
│   │   └── Sidebar.tsx               # Side panel with status
│   ├── services/
│   │   └── chatService.ts            # API client (streaming + transcript)
│   ├── assets/
│   │   └── WPI_ICON.jpg              # WPI logo
│   ├── App.tsx                       # Application shell
│   ├── types.ts                      # TypeScript types
│   ├── constants.ts                  # App constants
│   └── index.html                    # Entry point
│
├── backend/                           # FastAPI application
│   ├── app/
│   │   ├── agents/
│   │   │   ├── adviser_agent.py      # ReAct agent with tool use
│   │   │   ├── intent_agent.py       # Free-form LLM intent classification
│   │   │   ├── tools.py              # Agent tools (db, context, complexity)
│   │   │   └── streaming_callback.py # SSE streaming handler
│   │   ├── api/
│   │   │   ├── chat.py               # /api/chat endpoint (streaming)
│   │   │   └── transcript.py         # /api/extract-transcript endpoint
│   │   ├── services/
│   │   │   ├── program_db_service.py # SQLite database queries
│   │   │   ├── context_manager.py    # Student transcript caching
│   │   │   ├── pdf_extraction_service.py # Gemini Vision PDF extraction
│   │   │   └── conversation_memory.py # Redis conversation history
│   │   ├── schemas/
│   │   │   ├── chat.py               # Chat request/response models
│   │   │   └── transcript.py         # Transcript data models
│   │   └── main.py                   # FastAPI app setup
│   ├── tests/                        # Pytest test suite
│   ├── requirements.txt              # Python dependencies
│   └── .env.example                  # Environment template
│
├── database/
│   └── database_project/
│       ├── bus_school.db             # SQLite database (source of truth)
│       ├── setup_database.sql        # Database schema
│       └── wbs-courses.csv           # Course data
│
├── start.sh                          # Start both services
├── stop.sh                           # Stop both services
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

### PDF Transcript Extraction
- **Gemini Vision API** - OCR + LLM extraction
- **Structured output** - Student name, ID, GPA, courses, grades
- **Context caching** - 60-minute TTL for personalized responses

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

### Backend Environment (.env)

```bash
# Required
GOOGLE_API_KEY=your_google_gemini_api_key

# Optional
FRONTEND_URL=http://localhost:5173
LOG_LEVEL=INFO
REDIS_URL=redis://localhost:6379  # For conversation memory
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
| Frontend | React 18 + TypeScript + Vite |
| Styling | TailwindCSS |
| Backend | FastAPI + Python 3.12 |
| LLM | Google Gemini 2.5 Flash |
| Agent Framework | LangChain |
| Database | SQLite |
| Streaming | Server-Sent Events (SSE) |
| PDF Extraction | Gemini Vision API |

## License

MIT License - see LICENSE file for details.
