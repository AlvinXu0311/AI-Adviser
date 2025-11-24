"""System status API endpoints for component health checks."""
from datetime import datetime, timezone
import logging
import os
from typing import Dict

from fastapi import APIRouter

from ..services.rag_service import get_rag_service

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
    """Verify the in-memory RAG index is ready."""
    try:
        rag_service = get_rag_service()
        documents = getattr(rag_service, "documents", []) or []
        bm25_ready = getattr(rag_service, "bm25", None) is not None

        if documents and bm25_ready:
            return _status_payload(
                "vector_db",
                "Vector DB",
                "online",
                f"Indexed documents: {len(documents)}"
            )

        reason = "BM25 index unavailable" if not bm25_ready else "No documents loaded"
        return _status_payload("vector_db", "Vector DB", "offline", reason)
    except Exception as exc:  # pragma: no cover - defensive logging
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
        from google import genai  # type: ignore
    except Exception as exc:  # pragma: no cover - import guard
        return _status_payload("gemini", "Gemini", "offline", f"SDK missing: {exc}")

    try:
        client = genai.Client(api_key=api_key)
        probe_text = "health check"

        # Prefer low-cost token counting; fall back to tiny generation if unavailable
        count_tokens = getattr(client.models, "count_tokens", None)
        if callable(count_tokens):
            count_tokens(model=model_name, contents=probe_text)
        else:
            client.models.generate_content(model=model_name, contents=probe_text)

        return _status_payload(
            "gemini",
            "Gemini",
            "online",
            f"Model {model_name} reachable"
        )
    except Exception as exc:  # pragma: no cover - external dependency
        logger.exception("Gemini status check failed")
        return _status_payload("gemini", "Gemini", "offline", str(exc))


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
