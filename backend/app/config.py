"""Shared LLM settings."""
import os

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"


def gemini_model() -> str:
    """Gemini model used by every backend LLM call; override with the GEMINI_MODEL env var."""
    return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def legacy_request_options() -> dict:
    """
    request_options for the google.generativeai SDK (transcript OCR, chat summary):
    a per-attempt deadline plus exponential-backoff retries on 429 / 5xx / deadline errors.
    """
    from google.api_core import exceptions, retry

    timeout = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "60"))
    retryable = retry.if_exception_type(
        exceptions.TooManyRequests,
        exceptions.ResourceExhausted,
        exceptions.InternalServerError,
        exceptions.ServiceUnavailable,
        exceptions.DeadlineExceeded,
    )
    return {
        "timeout": timeout,
        "retry": retry.Retry(predicate=retryable, initial=1.0, maximum=20.0, multiplier=2.0,
                             timeout=timeout * (int(os.getenv("GEMINI_MAX_RETRIES", "3")) + 1)),
    }
