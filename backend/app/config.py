"""Shared LLM settings."""
import os

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"


def gemini_model() -> str:
    """Gemini model used by every backend LLM call; override with the GEMINI_MODEL env var."""
    return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
