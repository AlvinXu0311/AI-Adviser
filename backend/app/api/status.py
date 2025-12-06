"""System status API endpoints for component health checks."""
from datetime import datetime, timezone
import logging
import os
from typing import Dict

from fastapi import APIRouter

from ..services.vector_search_service import get_vector_search_service

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
    """Verify the ChromaDB vector search service is ready."""
    try:
        vector_service = get_vector_search_service()

        # Check if collections are initialized and have data
        collections = getattr(vector_service, "collections", {})
        if not collections:
            return _status_payload(
                "vector_db",
                "Vector DB",
                "offline",
                "Collections not initialized"
            )

        # Count total indexed items across all collections
        total_items = 0
        collection_details = []

        for entity_type, collection in collections.items():
            count = collection.count()
            total_items += count
            collection_details.append(f"{entity_type.value}: {count}")

        if total_items > 0:
            details = f"Indexed {total_items} items ({', '.join(collection_details)})"
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
            "No documents indexed"
        )
    except Exception as exc:
        logger.exception("Vector DB status check failed")
        return _status_payload("vector_db", "Vector DB", "offline", str(exc))


def _check_gemini() -> Dict[str, str]:
    """Perform a lightweight request against Gemini to verify availability."""
    provider = os.getenv("LLM_PROVIDER", "google").lower()
    if provider != "google":
        return _status_payload(
            "gemini",
            "Gemini",
            "offline",
            f"LLM provider set to '{provider}'"
        )

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return _status_payload(
            "gemini",
            "Gemini",
            "offline",
            "GOOGLE_API_KEY is not configured"
        )

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

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
        error_msg = str(exc)
        # Truncate error message if too long
        if len(error_msg) > 100:
            error_msg = error_msg[:100] + "..."
        return _status_payload("gemini", "Gemini", "offline", error_msg)


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
async def get_system_status():
    """Return health for the core subsystems used by the adviser."""
    components = [
        _check_vector_db(),
        _check_gemini(),
        _check_streaming(),
    ]

    overall = "online" if all(c["status"] == "online" for c in components) else "degraded"

    return {
        "overall_status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }
