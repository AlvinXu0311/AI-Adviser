"""
Main FastAPI application for WPI Business School Chatbot.
Uses Google Gemini for all LLM calls.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .api.auth import router as auth_router
from .api.chat import router as chat_router
from .api.transcript import router as transcript_router
from .api.status import router as status_router
from .api.summary import router as summary_router
from .api.admin import router as admin_router
from .auth import _jwt_secret
from .observability import setup_tracing
from .schemas.transcript import MAX_TRANSCRIPT_BASE64_CHARS
from dotenv import load_dotenv
import os
import logging
from langchain_core.globals import set_debug

# Enable LangChain debug mode for troubleshooting (can be disabled with env var)
set_debug(os.getenv("LANGCHAIN_DEBUG", "false").lower() == "true")

# Configure logging - default to INFO for production, DEBUG via env var
log_level = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Startup diagnostics: log which Python executable is running and whether redis is importable
try:
    import sys
    logger.info(f"Python executable: {sys.executable}")
    try:
        import redis as _redis
        logger.info(f"redis package available: version={getattr(_redis, '__version__', 'unknown')}")
    except Exception as e:
        logger.warning(f"redis import test failed at startup: {e}")
except Exception:
    # Non-fatal - diagnostics only
    pass

load_dotenv()

app = FastAPI(
    title="WPI Business School Chatbot API",
    description="API for academic advising chatbot with transcript processing",
    version="1.0.0"
)

# Configure CORS - allow all origins for tunnel deployment
# For production, set FRONTEND_URL environment variable
default_frontend_origins = "http://localhost:3000,http://localhost:5173,http://localhost:5174,http://localhost:4200"
allowed_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_URL", default_frontend_origins).split(",")
    if origin.strip()
]

# Check if running with tunnel (CORS needs to allow the dynamic tunnel URLs)
allow_all_origins = os.getenv("ALLOW_ALL_ORIGINS", "false").lower() == "true"

if allow_all_origins:
    logger.info("CORS: Allowing all origins (tunnel mode)")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,  # Cannot use credentials with wildcard origin
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    logger.info(f"Allowed CORS origins: {allowed_origins}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Reject oversized bodies before they are read into memory (nginx enforces the same limit)
MAX_REQUEST_BYTES = MAX_TRANSCRIPT_BASE64_CHARS + 1024 * 1024


class BodySizeLimitMiddleware:
    """
    413 for request bodies over `max_bytes`: up front from Content-Length, and by counting bytes
    as they are received for chunked uploads that send no Content-Length.
    """

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        too_large = JSONResponse(status_code=413, content={"detail": "Request body too large"})
        content_length = dict(scope["headers"]).get(b"content-length", b"")
        if content_length.isdigit() and int(content_length) > self.max_bytes:
            return await too_large(scope, receive, send)

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # An HTTPException passes through FastAPI's body parsing and becomes a 413
                    raise HTTPException(status_code=413, detail="Request body too large")
            return message

        async def tracking_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except HTTPException as exc:
            if exc.status_code != 413 or response_started:
                raise
            await too_large(scope, receive, send)


app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)


@app.on_event("startup")
async def check_auth_config() -> None:
    """Refuse to start without a signing secret, instead of failing on the first login; set up tracing."""
    _jwt_secret()
    setup_tracing()
    if os.getenv("DEMO_LOGIN_ENABLED", "false").lower() == "true":
        logger.warning("Demo login is ENABLED (DEMO_LOGIN_ENABLED=true); disable it in production")


# Configure the legacy google.generativeai SDK (used by transcript extraction)
import google.generativeai as genai
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    logger.warning("GOOGLE_API_KEY environment variable not set")
else:
    genai.configure(api_key=api_key)
    logger.info("[INFO] Google Gemini API configured")

# Include routers
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(transcript_router, prefix="/api", tags=["transcript"])
app.include_router(status_router, prefix="/api", tags=["status"])
app.include_router(summary_router, prefix="/api", tags=["summary"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])


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