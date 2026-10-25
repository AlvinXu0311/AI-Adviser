"""
Context Manager Service - Session-based storage for student transcript data.

Transcript data is stored in Redis (key `student_context:{session_id}`), encrypted with
Fernet, so every backend worker sees the same data and it survives restarts. Sessions
expire CONTEXT_TTL_SECONDS (default: 24 hours) after their last access.

Set CONTEXT_STORE=memory to use an in-process fakeredis instead (tests and offline eval only).
"""
from typing import Optional, Dict, Any
from contextvars import ContextVar
from datetime import datetime
import base64
import hashlib
import json
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Default TTL: 24 hours (in seconds)
CONTEXT_TTL_SECONDS = int(os.getenv("CONTEXT_TTL_SECONDS", 86400))  # 24 hours
CONTEXT_KEY_PREFIX = "student_context:"

# Context variable to store current session_id for tool access
current_session_id: ContextVar[Optional[str]] = ContextVar('current_session_id', default=None)


def set_current_session(session_id: str) -> None:
    """Set the current session ID for tool access."""
    current_session_id.set(session_id)


def get_current_session() -> Optional[str]:
    """Get the current session ID for tool access."""
    return current_session_id.get()


class StudentContext:
    """Stores extracted transcript data for a single student session."""

    def __init__(self):
        self.student_name: Optional[str] = None
        self.student_id: Optional[str] = None
        self.email: Optional[str] = None
        self.degree_program: Optional[str] = None
        self.gpa: Optional[float] = None
        self.courses: list[dict] = []  # Completed courses
        self.current_courses: list[dict] = []  # Currently enrolled courses
        self.transcript_text: Optional[str] = None
        self.raw_data: Optional[Dict[str, Any]] = None
        self.created_at: datetime = datetime.now()

    def update_from_transcript(self, transcript_data: Dict[str, Any]) -> None:
        """Update context from extracted transcript data."""
        self.student_name = transcript_data.get("student_name")
        self.student_id = transcript_data.get("student_id")
        self.email = transcript_data.get("email")
        self.degree_program = transcript_data.get("degree_program")
        self.gpa = transcript_data.get("gpa")
        self.courses = transcript_data.get("courses", [])
        self.current_courses = transcript_data.get("current_courses", [])
        self.transcript_text = transcript_data.get("transcript_text")
        self.raw_data = transcript_data

    def has_transcript(self) -> bool:
        """Check if transcript data has been uploaded."""
        return bool(self.courses) or bool(self.transcript_text)


def _fernet() -> Fernet:
    """CONTEXT_ENCRYPTION_KEY (a Fernet key) if set, otherwise a key derived from APP_JWT_SECRET."""
    key = os.getenv("CONTEXT_ENCRYPTION_KEY")
    if key:
        return Fernet(key.encode())
    secret = os.getenv("APP_JWT_SECRET", "")
    if not secret:
        raise RuntimeError("Set CONTEXT_ENCRYPTION_KEY or APP_JWT_SECRET to encrypt transcript data")
    digest = hashlib.sha256(b"student-context:" + secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class ContextManager:
    """
    Redis-backed, encrypted student context per session_id.

    Each read refreshes the TTL, so active sessions stay alive and idle ones expire.
    Eviction under memory pressure is left to Redis' maxmemory policy.
    """

    def __init__(self, redis_client, ttl_seconds: int = None):
        self.redis = redis_client
        self.ttl_seconds = ttl_seconds or CONTEXT_TTL_SECONDS
        self._fernet = _fernet()

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{CONTEXT_KEY_PREFIX}{session_id}"

    def get_student_context(self, session_id: str) -> StudentContext:
        """
        Get the student context for a session (empty if none was uploaded or it expired).

        Args:
            session_id: The unique session identifier from the frontend

        Returns:
            StudentContext for this session
        """
        context = StudentContext()
        key = self._key(session_id)
        blob = self.redis.get(key)
        if blob is None:
            return context
        try:
            data = json.loads(self._fernet.decrypt(blob.encode() if isinstance(blob, str) else blob))
        except (InvalidToken, ValueError):
            logger.warning(f"Discarding unreadable student context for session {session_id[:8]}...")
            self.redis.delete(key)
            return context
        self.redis.expire(key, self.ttl_seconds)
        context.update_from_transcript(data)
        return context

    def set_student_context(self, session_id: str, transcript_data: Dict[str, Any]) -> None:
        """
        Set student context from extracted transcript data.

        Args:
            session_id: The unique session identifier
            transcript_data: Extracted transcript data dictionary
        """
        blob = self._fernet.encrypt(json.dumps(transcript_data, default=str).encode())
        self.redis.set(self._key(session_id), blob, ex=self.ttl_seconds)
        logger.info(f"Updated student context for session {session_id[:8]}... "
                   f"Courses: {len(transcript_data.get('courses') or [])}")

    def clear_student_context(self, session_id: str) -> None:
        self.redis.delete(self._key(session_id))

    def has_context(self, session_id: str) -> bool:
        """
        Check if a session has transcript data.

        Args:
            session_id: The unique session identifier

        Returns:
            True if session has uploaded transcript data
        """
        return self.get_student_context(session_id).has_transcript()

    def get_stats(self) -> Dict[str, Any]:
        """Get context manager statistics."""
        return {
            "sessions_with_transcript": sum(1 for _ in self.redis.scan_iter(match=f"{CONTEXT_KEY_PREFIX}*")),
            "ttl_seconds": self.ttl_seconds,
        }

# Global singleton instance
_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """Get the global context manager instance."""
    global _context_manager
    if _context_manager is None:
        if os.getenv("CONTEXT_STORE", "redis").lower() == "memory":
            import fakeredis
            client = fakeredis.FakeRedis()
            logger.warning("ContextManager is using in-process fakeredis (CONTEXT_STORE=memory)")
        else:
            from .conversation_memory import get_conversation_memory
            client = get_conversation_memory().redis_client
        _context_manager = ContextManager(client)
        logger.info("Initialized Redis-backed ContextManager")
    return _context_manager
