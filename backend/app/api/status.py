"""System status API endpoints for component health checks."""
from datetime import datetime, timezone
import logging
import os
from typing import Dict

import asyncio

from fastapi import APIRouter, Depends

from ..auth import User
from ..services.rate_limit import rate_limited
from ..config import gemini_model
from ..services.pdf_vector_service import get_pdf_vector_service

router = APIRouter()
logger = logging.getLogger(__name__)


def _status_payload(
    key: str,
    label: str,
    status: str,
    details: str = ""
) -> Dict[str, str]:
    """Helper to keep component payloads consistent."""
    return {
        "key": key,
        "label": label,
        "status": status,
        "details": details,
    }


def _check_vector_db() -> Dict[str, str]:
    """Verify the ChromaDB PDF vector search service is ready."""
    try:
        pdf_service = get_pdf_vector_service()
        stats = pdf_service.get_stats()
        
        total_chunks = stats.get("total_chunks", 0)
        embedding_type = stats.get("embedding_type", "unknown")
        
        if total_chunks > 0:
            details = f"Indexed {total_chunks} chunks from PDFs ({embedding_type} embeddings)"
            return _status_payload(
                "vector_db",
                "Vector DB",
                "online",
                details
            )

        return _status_payload(
            "vector_db",
            "Vector DB",
            "offline",
            "No PDF documents indexed"
        )
    except Exception as exc:
        logger.exception("Vector DB status check failed")
        return _status_payload("vector_db", "Vector DB", "offline", "Vector index unavailable")


def _check_gemini() -> Dict[str, str]:
    """Perform a lightweight request against Gemini to verify availability."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return _status_payload(
            "gemini",
            "Gemini",
            "offline",
            "GOOGLE_API_KEY is not configured"
        )

    model_name = gemini_model()

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except Exception as exc:
        return _status_payload("gemini", "Gemini", "offline", f"SDK missing: {exc}")

    try:
        # Use LangChain's ChatGoogleGenerativeAI for health check
        # API key is automatically picked up from GOOGLE_API_KEY env var
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0
        )

        # Simple invoke test - lightweight
        _ = llm.invoke("test")

        return _status_payload(
            "gemini",
            "Gemini",
            "online",
            f"Model {model_name} reachable"
        )
    except Exception as exc:
        logger.exception("Gemini status check failed")
        return _status_payload("gemini", "Gemini", "offline", "Model unreachable")


def _check_streaming() -> Dict[str, str]:
    """Report whether SSE streaming is enabled server-side."""
    streaming_disabled = os.getenv("STREAMING_DISABLED", "false").lower() == "true"

    if streaming_disabled:
        return _status_payload(
            "streaming",
            "Streaming",
            "offline",
            "STREAMING_DISABLED=true"
        )

    return _status_payload(
        "streaming",
        "Streaming",
        "online",
        "Server-Sent Events enabled"
    )


@router.get("/status")
async def get_system_status(
    user: User = Depends(rate_limited("status", "STATUS_RATE_LIMIT_PER_MINUTE", 6, 60)),
):
    """Return health for the core subsystems used by the adviser (makes a real Gemini call)."""
    # Both checks block (Chroma read, Gemini round trip), so run them in threads concurrently
    vector_db, gemini = await asyncio.gather(
        asyncio.to_thread(_check_vector_db), asyncio.to_thread(_check_gemini)
    )
    components = [vector_db, gemini, _check_streaming()]

    overall = "online" if all(c["status"] == "online" for c in components) else "degraded"

    return {
        "overall_status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }
