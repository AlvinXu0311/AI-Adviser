"""
Context Manager Service - Session-based storage for student transcript data.

Each browser session gets its own isolated student context, preventing data leakage
between different users.

Expiration: Sessions expire after CONTEXT_TTL_SECONDS (default: 24 hours).
"""
from typing import Optional, Dict, Any
from contextvars import ContextVar
from datetime import datetime, timedelta
import logging
import os

logger = logging.getLogger(__name__)

# Default TTL: 24 hours (in seconds)
CONTEXT_TTL_SECONDS = int(os.getenv("CONTEXT_TTL_SECONDS", 86400))  # 24 hours
# Max sessions to keep in memory
MAX_CONTEXT_SESSIONS = int(os.getenv("MAX_CONTEXT_SESSIONS", 1000))

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
        self.last_accessed: datetime = datetime.now()
    
    def touch(self) -> None:
        """Update last accessed time to keep session alive."""
        self.last_accessed = datetime.now()
    
    def is_expired(self, ttl_seconds: int = CONTEXT_TTL_SECONDS) -> bool:
        """Check if this context has expired."""
        return datetime.now() - self.last_accessed > timedelta(seconds=ttl_seconds)
    
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


class ContextManager:
    """
    Session-based context manager with automatic expiration.
    
    Stores student context per session_id, ensuring each browser session
    has isolated data.
    
    Expiration strategies:
    - TTL: Sessions expire after CONTEXT_TTL_SECONDS (default: 24 hours)
    - Max sessions: Oldest sessions evicted when exceeding MAX_CONTEXT_SESSIONS
    """
    
    def __init__(self, ttl_seconds: int = None, max_sessions: int = None):
        # Dictionary mapping session_id to StudentContext
        self._sessions: Dict[str, StudentContext] = {}
        self.ttl_seconds = ttl_seconds or CONTEXT_TTL_SECONDS
        self.max_sessions = max_sessions or MAX_CONTEXT_SESSIONS
    
    def _cleanup_expired(self) -> int:
        """Remove expired sessions. Called automatically on access."""
        expired = [
            sid for sid, ctx in self._sessions.items()
            if ctx.is_expired(self.ttl_seconds)
        ]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")
        return len(expired)
    
    def _evict_oldest_if_needed(self) -> None:
        """Evict oldest sessions if exceeding max_sessions limit (LRU policy)."""
        if len(self._sessions) >= self.max_sessions:
            # Sort by last_accessed, evict oldest 10%
            sorted_sessions = sorted(
                self._sessions.items(),
                key=lambda x: x[1].last_accessed
            )
            evict_count = max(1, len(sorted_sessions) // 10)
            for sid, _ in sorted_sessions[:evict_count]:
                del self._sessions[sid]
            logger.info(f"Evicted {evict_count} oldest sessions (LRU)")
    
    def get_student_context(self, session_id: str) -> StudentContext:
        """
        Get or create student context for a session.
        
        Args:
            session_id: The unique session identifier from the frontend
            
        Returns:
            StudentContext for this session
        """
        # Periodic cleanup (every access)
        self._cleanup_expired()
        
        if session_id not in self._sessions:
            self._evict_oldest_if_needed()
            logger.info(f"Creating new student context for session: {session_id[:8]}...")
            self._sessions[session_id] = StudentContext()
        else:
            # Touch to keep alive
            self._sessions[session_id].touch()
        
        return self._sessions[session_id]
    
    def set_student_context(self, session_id: str, transcript_data: Dict[str, Any]) -> None:
        """
        Set student context from extracted transcript data.
        
        Args:
            session_id: The unique session identifier
            transcript_data: Extracted transcript data dictionary
        """
        context = self.get_student_context(session_id)
        context.update_from_transcript(transcript_data)
        context.touch()
        logger.info(f"Updated student context for session {session_id[:8]}... "
                   f"Student: {context.student_name}, Courses: {len(context.courses)}")
    
    def has_context(self, session_id: str) -> bool:
        """
        Check if a session has transcript data.
        
        Args:
            session_id: The unique session identifier
            
        Returns:
            True if session has uploaded transcript data
        """
        if session_id not in self._sessions:
            return False
        ctx = self._sessions[session_id]
        if ctx.is_expired(self.ttl_seconds):
            del self._sessions[session_id]
            return False
        return ctx.has_transcript()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get context manager statistics."""
        self._cleanup_expired()
        return {
            "active_sessions": len(self._sessions),
            "ttl_seconds": self.ttl_seconds,
            "max_sessions": self.max_sessions,
            "sessions_with_transcript": sum(
                1 for ctx in self._sessions.values() if ctx.has_transcript()
            )
        }
    
# Global singleton instance
_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """Get the global context manager instance."""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
        logger.info("Initialized session-based ContextManager")
    return _context_manager
