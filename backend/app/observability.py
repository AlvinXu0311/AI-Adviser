"""
LangSmith tracing.

Off unless LANGSMITH_TRACING=true and LANGSMITH_API_KEY are set. When on, each chat turn
is one trace: a `chat_turn` root with the intent classifier and the LangGraph adviser
(every LLM call and tool call) nested under it, grouped into a LangSmith thread by
session id. Transcript OCR and chat summaries call Gemini directly, outside LangChain,
and are traced through `traced_opaque`, which records timing and errors but no content.

Student data: `setup_tracing()` installs one Client as LangSmith's global default, so every
run (chat, background compaction, status checks) goes through its anonymizer, which masks
emails, student IDs and labelled names before anything leaves the process (LANGSMITH_REDACT_PII=false
turns that off, e.g. for a non-production project). Users are identified only by a
keyed hash, never by email.
"""
import contextlib
import hashlib
import hmac
import logging
import os
from functools import lru_cache
from typing import Any, Callable, Dict, Iterator, Optional

import langsmith
from langsmith.anonymizer import create_anonymizer

logger = logging.getLogger(__name__)

REDACTION_RULES = [
    # Emails
    {"pattern": r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "replace": "<email>"},
    # WPI-style IDs (A00123456, 900000001) and other 8-10 digit numbers
    {"pattern": r"\b[A-Z]?\d{8,10}\b", "replace": "<id>"},
    # Labelled names, as they appear in agent input, tool output and transcript text
    {"pattern": r"(?i)\b((?:student[ _]?)?name|student)\b(\"?\s*[:=]\s*\"?)[^\n,\"}]+",
     "replace": r"\1\2<name>"},
]


def tracing_enabled() -> bool:
    return (os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
            and bool(os.getenv("LANGSMITH_API_KEY")))


def project_name() -> str:
    return os.getenv("LANGSMITH_PROJECT", "wpi-adviser")


@lru_cache(maxsize=1)
def get_client() -> langsmith.Client:
    """The one LangSmith client every trace is sent through (so redaction cannot be bypassed)."""
    redact = os.getenv("LANGSMITH_REDACT_PII", "true").lower() != "false"
    if not redact:
        logger.warning("LangSmith PII redaction is OFF (LANGSMITH_REDACT_PII=false)")
    return langsmith.Client(anonymizer=create_anonymizer(REDACTION_RULES) if redact else None)


def user_hash(user_id: str) -> str:
    """Stable pseudonymous user id for trace metadata (keyed, so it can't be reversed by guessing)."""
    key = os.getenv("APP_JWT_SECRET", "").encode()
    return hmac.new(key, user_id.encode(), hashlib.sha256).hexdigest()[:16]


@contextlib.contextmanager
def chat_turn_trace(session_id: str, user_id: str, inputs: Dict[str, Any]) -> Iterator[Optional[Any]]:
    """
    Root run for one chat turn; LangChain/LangGraph runs started inside nest under it.
    Yields the RunTree (call `.end(outputs=...)` / `.add_metadata(...)`), or None when tracing is off.
    """
    if not tracing_enabled():
        yield None
        return
    metadata = {
        # LangSmith groups runs that share session_id into one conversation thread
        "session_id": session_id,
        "user": user_hash(user_id),
        "environment": os.getenv("ENVIRONMENT", "production"),
    }
    with langsmith.tracing_context(enabled=True, client=get_client(), project_name=project_name(),
                                   metadata=metadata):
        with langsmith.trace("chat_turn", run_type="chain", inputs=inputs, client=get_client(),
                             project_name=project_name(), metadata=metadata) as run:
            yield run


def traced_opaque(name: str, describe_inputs: Callable[[dict], dict],
                  describe_outputs: Callable[[Any], dict]) -> Callable:
    """
    Trace a function that handles raw student documents: only the shapes returned by
    `describe_inputs` / `describe_outputs` (sizes, counts) are recorded, never the content.
    """
    # traceable checks at call time whether tracing is on, and is a pass-through when it is off
    return langsmith.traceable(name=name, run_type="chain",
                               process_inputs=describe_inputs, process_outputs=describe_outputs)


def setup_tracing() -> None:
    """Call once at startup: make the redacting client the default for every LangSmith run."""
    if not tracing_enabled():
        logger.info("LangSmith tracing disabled")
        return
    langsmith.configure(client=get_client(), project_name=project_name(),
                        metadata={"environment": os.getenv("ENVIRONMENT", "production")})
    logger.info("LangSmith tracing enabled (project=%s, redaction=%s)", project_name(),
                os.getenv("LANGSMITH_REDACT_PII", "true").lower() != "false")
