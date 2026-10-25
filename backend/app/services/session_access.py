"""
Session ownership: every chat session belongs to the authenticated user who first used it.

The owner is stored in Redis (`session_owner:{session_id}`) with the same TTL as the chat
history. Any later request for that session from a different user gets 403, so knowing a
session id is not enough to read or delete someone else's conversation or transcript.
"""
import logging
import re

from fastapi import HTTPException, status

from ..auth import User
from .conversation_memory import DEFAULT_SESSION_TTL, get_conversation_memory

logger = logging.getLogger(__name__)

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def owner_key(session_id: str) -> str:
    return f"session_owner:{session_id}"


def _validate(session_id: str) -> None:
    if not SESSION_ID_RE.fullmatch(session_id or ""):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid session id")


def claim_session(session_id: str, user: User) -> None:
    """Bind an unused session id to this user, or check that the user already owns it."""
    _validate(session_id)
    redis = get_conversation_memory().redis_client
    key = owner_key(session_id)
    if not redis.set(key, user.id, nx=True, ex=DEFAULT_SESSION_TTL):
        if redis.get(key) != user.id:
            logger.warning("User %s denied access to session %s...", user.id, session_id[:8])
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This session belongs to another user")
        redis.expire(key, DEFAULT_SESSION_TTL)


def require_session_owner(session_id: str, user: User) -> None:
    """Like claim_session, but the session must already exist."""
    _validate(session_id)
    owner = get_conversation_memory().redis_client.get(owner_key(session_id))
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if owner != user.id:
        logger.warning("User %s denied access to session %s...", user.id, session_id[:8])
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This session belongs to another user")


def release_session(session_id: str) -> None:
    get_conversation_memory().redis_client.delete(owner_key(session_id))
