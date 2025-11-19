# WPI Business School Digital Library Chatbot

Interactive chatbot platform for academic advising with PDF transcript upload, agentic RAG, and LangChain-powered responses.

## Quick Start

### Prerequisites

- Node.js 16+ (for frontend)
- Python 3.8+ (for backend)
- Google Gemini API key
- (Optional) Ollama for local Llama 3.1 support

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

### Optional: local backend venv (manual)

If you prefer to run the backend manually inside a virtual environment instead of using `./start.sh`, create and activate a venv and install backend requirements:

```bash
# from project root
python3 -m venv backend/venv
source backend/venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt
python -m uvicorn app.main:app --reload
```
### Manual Start

**Terminal 1: Backend**
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add GOOGLE_API_KEY
python -m uvicorn app.main:app --reload
```

**Terminal 2: Frontend**
```bash
cd frontend
npm install
npm start
```

### Access the Application

- **Frontend**: http://localhost:4200
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## Project Structure

```
AI-Adviser/
├── frontend/                           # Angular 15 application
│   ├── src/app/
│   │   ├── components/pdf-upload/     # PDF upload component (30 tests)
│   │   ├── services/                  # Chat & PDF services
│   │   └── app.component.ts           # Main app (23 tests)
│   ├── package.json                   # Dependencies
│   └── README.md                       # Frontend documentation
│
├── backend/                            # FastAPI application with LangChain
│   ├── app/
│   │   ├── agents/                    # LangChain agents (NEW)
│   │   │   ├── adviser_agent.py      # Academic adviser ReAct agent
│   │   │   ├── tools.py              # Agent tools (RAG, context, analysis)
│   │   │   └── __init__.py
│   │   ├── chains/                    # LangChain chains (NEW)
│   │   │   ├── rag_chain.py          # Hybrid RAG with BM25 + semantic search
│   │   │   ├── chat_chain.py         # Context-aware chat chain
│   │   │   └── __init__.py
│   │   ├── api/                       # REST endpoints (chat, transcript)
│   │   ├── services/                  # Business logic
│   │   │   ├── llm_service.py        # LLM utilities
│   │   │   ├── rag_service.py        # RAG retrieval system
│   │   │   ├── context_manager.py    # Student context caching
│   │   │   └── pdf_extraction_service.py
│   │   ├── schemas/                   # Data validation
│   │   ├── knowledge_base/           # RAG knowledge base (programs.json)
│   │   └── utils/                     # Error handling
│   ├── tests/                         # 45+ test cases
│   ├── requirements.txt               # Python dependencies (including LangChain)
│   ├── .env.example                   # Environment template
│   └── pytest.ini                     # Test configuration
│
├── database/                           # Database structure NEW
│   ├── models/                        # SQLAlchemy models
│   ├── migrations/                    # Database migrations
│   ├── backups/                       # Database backups (gitignored)
│   ├── data/                          # Data files (gitignored)
│   ├── scripts/                       # Utility scripts
│   │   ├── init_db.py                # Initialize database
│   │   └── backup_db.sh              # Backup script
│   └── README.md                      # Database documentation
│
├── .gitignore                         # Git exclusions (updated)
├── start.sh                           # Start both services
├── stop.sh                            # Stop both services
├── README.md                          # This file
│
├── BACKEND_TESTING_GUIDE.md           # Backend testing documentation
├── FRONTEND_TESTING_GUIDE.md          # Frontend testing documentation
├── QUICK_TEST_GUIDE.md                # Quick reference for tests
├── IMPLEMENTATION_SUMMARY.md          # Complete implementation details
├── API_CONTRACT.md                    # API specifications
├── BACKEND_ROADMAP.md                 # Backend architecture guide
│
├── CoT_Implementation_Guide.md        # Chain of Thought guide NEW
├── CoT_Implementation_Summary.md      # CoT summary NEW
├── RAG_Performance_Improvement_Analysis.md  # RAG improvements NEW
├── Project_Cleanup_Summary.md         # Project cleanup NEW
└── Emoji_Cleanup_Summary.md           # Emoji removal summary NEW
```

## Frontend Features

**User Interface**
- Professional Material Design with gradient theme
- Responsive layout (desktop, tablet, mobile)
- Real-time message updates with auto-scroll
- Loading indicators and progress tracking

**PDF Upload**
- Drag-and-drop interface
- File validation (PDF type check)
- Progress indicator
- Extracted data preview (student info, courses, GPA)

**Chat**
- Message history with timestamps
- Context-aware responses using student data
- Error handling with user-friendly messages
- Auto-scroll to latest message

**Technology Stack**
- Frontend: Angular + TypeScript
- Backend: FastAPI + Python
- Agent framework: LangChain (with Google GenAI / Gemini integrations)
- Vector DB (optional): Chroma
- Embeddings: Sentence-Transformers
- Keyword retrieval: Rank-BM25
- ORM: SQLAlchemy
- Testing: Pytest (backend), Jasmine/Karma (frontend)
- Package managers: pip (backend), npm (frontend)

## Backend Features

**API Endpoints**

1. **POST /api/chat** - Chat with LangChain agentic RAG
   - Accepts: `{ message, transcriptContext? }`
   - Returns: `{ response, intent, response_source }`
   - Uses LangChain ReAct agent for autonomous reasoning
   - Hybrid RAG retrieval (BM25 + semantic search)
   - Tool-based knowledge lookup and context analysis

2. **POST /api/extract-transcript** - Extract from PDF
   - Accepts: `{ pdf_base64 }`
   - Returns: `{ success, data, error? }`
   - Uses Gemini Vision API for OCR extraction

3. **GET /api/health** - Health check
   - Returns: `{ status, service, version }`

4. **GET /** - Root endpoint
   - Returns: `{ message }`

**LangChain Architecture**

Agents (Autonomous Reasoning):
- **AdviserAgent**: ReAct pattern for multi-step reasoning
  - Autonomous tool invocation for knowledge retrieval
  - Step-by-step reasoning about student queries
  - Integration of multiple information sources
  - Intelligent decision-making with tool use

Chains (Processing Pipelines):
- **RAGChain**: Hybrid retrieval with ensemble methods
  - BM25 retrieval for keyword matching (50% weight)
  - Semantic search with embeddings (50% weight)
  - Ensemble retriever combining both approaches
  - Relevance scoring and confidence calculation

- **ChatChain**: Context-aware conversation
  - Student transcript context integration
  - Conversation history management
  - CoT-inspired reasoning patterns
  - System prompt customization

Tools (Agent Capabilities):
- **RAG Search**: Query program knowledge base
- **Student Context**: Access transcript information
- **Complexity Assessment**: Analyze query requirements

**Core Services**

- **RAGService**: Retrieval-Augmented Generation
  - BM25 scoring for relevance ranking
  - Program information retrieval from knowledge base
  - Context generation for LLM prompts
  - Top-K retrieval with relevance filtering

- **PDFExtractionService**: Intelligent transcript extraction
  - Gemini Vision API for OCR
  - Regex-based extraction with LLM fallback
  - Structured data extraction (GPA, courses, grades)

- **ContextManager**: Student context caching
  - 60-minute TTL for transcript data
  - Academic progress evaluation
  - Course progression tracking

**Data Models**

```typescript
// Request to chat endpoint
{
  message: "What courses should I take?",
  transcriptContext: {
    studentName: "John Doe",
    gpa: 3.85,
    program: "MS in Business Analytics",
    courseCount: 6
  }
}

// Response with extracted transcript
{
  success: true,
  data: {
    studentName: "John Doe",
    studentId: "A00123456",
    gpa: 3.85,
    completedCourses: [...],
    currentCourses: [...],
    programInfo: {...}
  }
}
```

**Advanced Features**
- Agentic RAG with ReAct pattern (reasoning and acting)
- Hybrid retrieval combining BM25 and semantic search
- Autonomous agent tool invocation for knowledge queries
- RAG (Retrieval-Augmented Generation) for program information
- Student context caching with 60min TTL
- Academic progress evaluation and tracking
- Multi-tool agent reasoning with fallback mechanisms

## Testing

### Run All Tests

```bash
# Frontend (watch mode)
cd frontend && npm test

# Frontend (once)
cd frontend && npm test -- --watch=false

# Backend
cd backend && pytest

# Backend with coverage
cd backend && pytest --cov=app --cov-report=html
```

## Configuration

### Environment Setup

Create `backend/.env`:
```bash
# Required - Google Gemini API Key for LangChain integration
GOOGLE_API_KEY=your_google_gemini_api_key_here

# LangChain Configuration
# Enable/disable agentic RAG features
LANGCHAIN_ENABLED=true
LANGCHAIN_VERBOSE=false

# RAG Configuration
RAG_HYBRID_SEARCH=true        # Enable hybrid BM25 + semantic search
RAG_BM25_WEIGHT=0.5           # BM25 weight in ensemble (0.0-1.0)
RAG_SEMANTIC_WEIGHT=0.5       # Semantic weight in ensemble (0.0-1.0)
RAG_TOP_K=5                   # Number of top results to retrieve

# Vector Database
CHROMA_PERSIST_DIR=/tmp/chroma_db

# Server Configuration
FRONTEND_URL=http://localhost:4200
LOG_LEVEL=INFO
```

### API Configuration

Backend API URL is automatically set:
- Frontend: `http://localhost:8000/api` (in services)
- Backend CORS: Configured to allow `http://localhost:4200`

### Customization

**Change Port Numbers**
- Frontend: Edit `angular.json` (port 4200)
- Backend: Edit start.sh or run with `--port XXXX`

**Change API URL**
- Frontend: Update `chat.service.ts` apiUrl property
- Backend: Update CORS settings in `main.py`

## API Usage Examples

### Chat with Context

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What courses should I take next?",
    "transcriptContext": {
      "studentName": "John Doe",
      "gpa": 3.85,
      "program": "MS in Business Analytics",
      "courseCount": 6
    }
  }'
```

### Extract Transcript from PDF

```bash
curl -X POST http://localhost:8000/api/extract-transcript \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_base64": "JVBERi0xLjQKJeLj..."
  }'
```

### Health Check

```bash
curl http://localhost:8000/api/health
```

## Troubleshooting

### Port Already in Use

```bash
# Kill process on port 4200
lsof -ti :4200 | xargs kill -9

# Kill process on port 8000
lsof -ti :8000 | xargs kill -9
```

### API Key Issues

```bash
# Check if .env exists in backend
ls backend/.env

# If not, create from template
cp backend/.env.example backend/.env

# Edit and add your Google Gemini API key
nano backend/.env
```

### Dependency Issues

```bash
# Reinstall frontend dependencies
cd frontend && rm -rf node_modules && npm install

# Reinstall backend dependencies
cd backend && pip install --upgrade -r requirements.txt
```

### Tests Failing

```bash
# Check backend tests with verbose output
cd backend && pytest -v

# Check frontend tests
cd frontend && npm test -- --watch=false --browsers=ChromeHeadless
```

## Deployment

### Frontend Deployment

```bash
cd frontend
npm run build

# Output: dist/frontend/
# Deploy to: Firebase, Netlify, Vercel, or your server
```

### Backend Deployment

```bash
cd backend

# Option 1: Gunicorn
pip install gunicorn
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker

# Option 2: Docker
docker build -t wpi-chatbot:latest .
docker run -p 8000:8000 -e GOOGLE_API_KEY=xxx wpi-chatbot:latest

# Option 3: Cloud Run, Heroku, AWS Lambda, etc.
# Follow platform-specific deployment guides
```

### Production Checklist

- [ ] Set `FRONTEND_URL` environment variable for production domain
- [ ] Configure Google Gemini API key securely
- [ ] Enable HTTPS/TLS
- [ ] Set up monitoring and logging
- [ ] Configure CORS for production domain
- [ ] Run full test suite
- [ ] Review API Contract documentation
- [ ] Set up backups
- [ ] Configure rate limiting
- [ ] Test end-to-end flow

## Documentation

### Core Documentation
1. **README.md** (this file) - Project overview and quick start
2. **BACKEND_TESTING_GUIDE.md** - Comprehensive backend testing guide
3. **FRONTEND_TESTING_GUIDE.md** - Comprehensive frontend testing guide
4. **QUICK_TEST_GUIDE.md** - Quick reference for running tests
5. **IMPLEMENTATION_SUMMARY.md** - Complete implementation details
6. **API_CONTRACT.md** - API specifications with examples
7. **BACKEND_ROADMAP.md** - Backend architecture and implementation guide

### LangChain & Agentic RAG Documentation (NEW)
8. **LANGCHAIN_ARCHITECTURE.md** - LangChain integration guide (new)
   - Agent design and ReAct pattern
   - Tool definitions and capabilities
   - Chain architecture and workflows
   - Integration examples

9. **AGENTIC_RAG_GUIDE.md** - Agentic RAG implementation (new)
   - Autonomous reasoning patterns
   - Hybrid retrieval strategy
   - Tool invocation workflows
   - Performance optimization

10. **RAG_HYBRID_RETRIEVAL.md** - Hybrid search implementation (new)
    - BM25 keyword matching
    - Semantic search with embeddings
    - Ensemble retriever weights
    - Performance comparison

## Development Team

- **Frontend**: Angular 15 with Material Design
- **Backend**: FastAPI with Python
- **Testing**: Comprehensive test suites (98+ tests)
- **Documentation**: Complete guides and examples

## Support & Issues

**Quick Commands**:
```bash
./start.sh                    # Start both services
./stop.sh                     # Stop both services
npm test                      # Run frontend tests
pytest                        # Run backend tests
python database/scripts/init_db.py    # Initialize database
bash database/scripts/backup_db.sh    # Backup database
```

**New Documentation**:
- CoT_Implementation_Guide.md - Chain of Thought comprehensive guide
- RAG_Performance_Improvement_Analysis.md - RAG improvement roadmap
- Project_Cleanup_Summary.md - Organization improvements
- Emoji_Cleanup_Summary.md - Logging standardization
