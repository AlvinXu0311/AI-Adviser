"""
Main FastAPI application for WPI Business School Chatbot.
Supports multiple LLM providers (Google Gemini or Local Llama).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.chat import router as chat_router
from .api.transcript import router as transcript_router
from dotenv import load_dotenv
import os
import logging

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(
    title="WPI Business School Chatbot API",
    description="API for academic advising chatbot with transcript processing",
    version="1.0.0"
)

# Configure CORS
allowed_origins = os.getenv("FRONTEND_URL", "http://localhost:4200").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Angular frontend URL (configurable via env)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure LLM provider
llm_provider = os.getenv("LLM_PROVIDER", "google").lower()
logger.info(f"Initializing with LLM_PROVIDER: {llm_provider}")

if llm_provider == "google":
    # Configure Google Gemini only if using Google provider
    try:
        import google.generativeai as genai
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_API_KEY environment variable not set")
        else:
            genai.configure(api_key=api_key)
            logger.info("[INFO] Google Gemini API configured")
    except ImportError:
        logger.warning("google.generativeai not available - using Llama provider instead")
elif llm_provider == "llama":
    logger.info(f"[INFO] Using Local Llama provider (Ollama at {os.getenv('LLAMA_API_URL', 'http://localhost:11434/api')})")
else:
    logger.warning(f"Unknown LLM_PROVIDER: {llm_provider}. Using default 'google'")

# Include routers
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(transcript_router, prefix="/api", tags=["transcript"])


@app.get("/", tags=["health"])
async def root():
    """Health check endpoint"""
    return {"message": "Welcome to WPI Business School Chatbot API"}


@app.get("/api/health", tags=["health"])
async def health_check():
    """API health check endpoint"""
    return {
        "status": "healthy",
        "service": "WPI Business School Chatbot API",
        "version": "1.0.0"
    }