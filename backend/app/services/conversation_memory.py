"""
Redis-backed Conversation Memory Manager using LangChain.
Maintains conversation history per user/session with Redis persistence.
Uses LangChain's RedisChatMessageHistory for standard integrations.
"""
import logging
import os
from typing import List, Optional, Any, Dict
from datetime import datetime
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_community.chat_message_histories import RedisChatMessageHistory

logger = logging.getLogger(__name__)


class RedisConversationMemory:
    """
    Redis-backed conversation memory manager.
    Uses LangChain's RedisChatMessageHistory for standard message storage.
    Provides session-based conversation management with persistence.
    """

    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379, redis_db: int = 0):
        """
        Initialize Redis conversation memory.

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database number
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db

        # Try to connect to Redis with retries and URL support
        # Per policy: Redis is required. If Redis is not available, raise an exception.
        self.in_memory_store: Dict[str, List[Dict[str, Any]]] = {}

        try:
            import redis
            import time

            # Support REDIS_URL environment variable for flexibility
            redis_url = os.getenv("REDIS_URL")
            client = None

            if redis_url:
                try:
                    client = redis.from_url(redis_url, decode_responses=True)
                    logger.info(f"Attempting Redis connection via REDIS_URL")
                except Exception as ex:
                    logger.debug(f"Redis.from_url failed: {ex}")
                    client = None

            if client is None:
                client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=True,
                    socket_connect_timeout=5
                )

            # Try pinging Redis with a few retries to handle transient startup timing
            last_exc = None
            for attempt in range(3):
                try:
                    client.ping()
                    self.redis_client = client
                    logger.info(f"Connected to Redis at {redis_host}:{redis_port}")
                    break
                except Exception as e:
                    last_exc = e
                    logger.debug(f"Redis ping attempt {attempt+1} failed: {e}")
                    time.sleep(0.5)

            if not hasattr(self, "redis_client"):
                # No successful connection — raise an error (do not fall back)
                raise RuntimeError(f"Unable to connect to Redis at {redis_host}:{redis_port}: {last_exc}")

        except Exception as e:
            # Fail loudly: Redis is required
            logger.error(f"Redis initialization error: {e}")
            raise

    def get_chat_history(self, session_id: str) -> Any:
        """
        Get LangChain-compatible chat history for a session.
        Uses Redis if available, otherwise in-memory fallback.

        Args:
            session_id: Unique session identifier

        Returns:
            Chat history object for the session
        """
        # Redis must be available here; otherwise __init__ would have raised.
        # Try constructing RedisChatMessageHistory and raise on failure.
        try:
            # Different langchain-community versions expect different ctor args.
            # Try several common constructor signatures for compatibility.
            constructors = [
                ("connection", lambda: RedisChatMessageHistory(session_id=session_id, connection=self.redis_client)),
                ("client", lambda: RedisChatMessageHistory(session_id=session_id, client=self.redis_client)),
                ("redis_client", lambda: RedisChatMessageHistory(session_id=session_id, redis_client=self.redis_client)),
                ("redis_url", lambda: RedisChatMessageHistory(session_id=session_id, redis_url=os.getenv("REDIS_URL") or f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}")),
                ("host_port", lambda: RedisChatMessageHistory(session_id=session_id, host=self.redis_host, port=self.redis_port, db=self.redis_db)),
                # Fallback: try no args (some versions may pick up default redis settings)
                ("no_args", lambda: RedisChatMessageHistory(session_id=session_id)),
            ]

            last_exc = None
            for name, ctor in constructors:
                try:
                    hist = ctor()
                    logger.debug(f"RedisChatMessageHistory created using signature: {name}")
                    return hist
                except TypeError as te:
                    # Constructor signature mismatch; try next
                    logger.debug(f"RedisChatMessageHistory ctor '{name}' TypeError: {te}")
                    last_exc = te
                    continue
                except Exception as e:
                    # Other runtime errors (connection, etc.) — record and try next
                    logger.debug(f"RedisChatMessageHistory ctor '{name}' raised: {e}")
                    last_exc = e
                    continue

            # If none of the constructors worked, raise an error (do not fall back)
            logger.error(f"Error creating RedisChatMessageHistory with available signatures: {last_exc}")
            raise RuntimeError(f"Failed to create RedisChatMessageHistory: {last_exc}")
        except Exception:
            # Propagate exceptions to the caller — Redis is required.
            raise

    def _get_in_memory_history(self, session_id: str) -> "InMemoryChatHistory":
        """Get in-memory fallback history"""
        if session_id not in self.in_memory_store:
            self.in_memory_store[session_id] = []
        return InMemoryChatHistory(session_id, self.in_memory_store[session_id])

    def add_user_message(self, session_id: str, message: str) -> None:
        """Add a user message to conversation history"""
        history = self.get_chat_history(session_id)
        history.add_user_message(message)
        logger.debug(f"Added user message to session {session_id}")

    def add_ai_message(self, session_id: str, message: str) -> None:
        """Add an AI message to conversation history"""
        history = self.get_chat_history(session_id)
        history.add_ai_message(message)
        logger.debug(f"Added AI message to session {session_id}")

    def get_messages(self, session_id: str) -> List[BaseMessage]:
        """Get all messages in conversation history"""
        history = self.get_chat_history(session_id)
        return history.messages

    def get_recent_messages(self, session_id: str, n: int = 5) -> List[BaseMessage]:
        """Get the last n messages from conversation"""
        history = self.get_chat_history(session_id)
        messages = history.messages
        return messages[-n:] if messages else []

    def get_context_string(self, session_id: str, n: int = 5) -> str:
        """
        Get recent conversation context as formatted string for LLM.

        Args:
            session_id: Session to retrieve context for
            n: Number of recent messages to include

        Returns:
            Formatted conversation context
        """
        recent = self.get_recent_messages(session_id, n)
        if not recent:
            return "No prior conversation"

        context_parts = ["Recent conversation context:"]
        for msg in recent:
            if isinstance(msg, HumanMessage):
                role = "USER"
            elif isinstance(msg, AIMessage):
                role = "ASSISTANT"
            else:
                role = "OTHER"

            # Truncate long messages
            content = msg.content[:200] if msg.content else "(empty)"
            context_parts.append(f"{role}: {content}")

        return "\n".join(context_parts)

    def clear_history(self, session_id: str) -> None:
        """Clear conversation history for a session"""
        history = self.get_chat_history(session_id)
        history.clear()
        logger.info(f"Cleared conversation history for session {session_id}")

    def get_summary(self, session_id: str) -> str:
        """Get a summary of conversation topics"""
        messages = self.get_messages(session_id)
        if not messages:
            return "No conversation yet"

        # Extract user messages for topic analysis
        user_messages = [m.content for m in messages if isinstance(m, HumanMessage)]
        if not user_messages:
            return "No user messages"

        # Simple topic detection
        topics = set()
        keywords = {"MSIT", "MSBA", "MSM", "course", "requirement", "prerequisite", "specialization"}
        for msg in user_messages:
            msg_lower = msg.lower()
            for kw in keywords:
                if kw.lower() in msg_lower:
                    topics.add(kw)

        return f"Topics: {', '.join(sorted(topics)) if topics else 'general inquiries'}"

    def get_stats(self) -> Dict[str, Any]:
        """Get conversation memory statistics"""
        if self.redis_available:
            try:
                # Use SCAN iterator to avoid blocking Redis for large keyspaces
                try:
                    session_count = sum(1 for _ in self.redis_client.scan_iter())
                except Exception:
                    # Fallback to KEYS if SCAN not supported
                    keys = self.redis_client.keys("*")
                    session_count = len(keys)

                return {
                    "status": "redis_connected",
                    "redis_host": self.redis_host,
                    "redis_port": self.redis_port,
                    "active_sessions": session_count,
                    "backend": "redis"
                }
            except Exception as e:
                logger.error(f"Error getting Redis stats: {str(e)}")
                return {"status": "error", "error": str(e)}
        else:
            return {
                "status": "in_memory_fallback",
                "active_sessions": len(self.in_memory_store),
                "backend": "in_memory"
            }


class InMemoryChatHistory:
    """
    In-memory fallback chat history (compatible with RedisChatMessageHistory interface).
    Used when Redis is not available.
    """

    def __init__(self, session_id: str, messages_list: List[Dict[str, Any]]):
        self.session_id = session_id
        self.messages_list = messages_list
        self.messages: List[BaseMessage] = []
        self._load_messages()

    def _load_messages(self):
        """Load messages from list into BaseMessage objects"""
        self.messages = []
        for msg in self.messages_list:
            if msg.get("type") == "human":
                self.messages.append(HumanMessage(content=msg.get("content", "")))
            elif msg.get("type") == "ai":
                self.messages.append(AIMessage(content=msg.get("content", "")))

    def add_message(self, message: BaseMessage):
        """Add message to history"""
        self.messages.append(message)
        # Persist to list
        if isinstance(message, HumanMessage):
            self.messages_list.append({"type": "human", "content": message.content})
        elif isinstance(message, AIMessage):
            self.messages_list.append({"type": "ai", "content": message.content})

    def add_user_message(self, message: str):
        """Add user message"""
        self.add_message(HumanMessage(content=message))

    def add_ai_message(self, message: str):
        """Add AI message"""
        self.add_message(AIMessage(content=message))

    def clear(self):
        """Clear all messages"""
        self.messages.clear()
        self.messages_list.clear()


# Global singleton instance
_conversation_memory: Optional[RedisConversationMemory] = None


def get_conversation_memory() -> RedisConversationMemory:
    """Get or create global conversation memory instance"""
    global _conversation_memory
    if _conversation_memory is None:
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))

        _conversation_memory = RedisConversationMemory(
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db
        )
        logger.info("Initialized conversation memory (Redis)")

    return _conversation_memory


def generate_session_id(identifier: str = "") -> str:
    """
    Generate a unique session ID.

    Args:
        identifier: Optional user/session identifier to hash

    Returns:
        Unique session ID
    """
    import hashlib

    if identifier:
        return hashlib.md5(identifier.encode()).hexdigest()[:16]
    else:
        return hashlib.md5(str(datetime.now()).encode()).hexdigest()[:16]

    # Backwards-compatible wrappers expected by API


def get_history(session_id: str):
    """
    Backwards-compatible wrapper to return a serializable conversation history.
    Returns a list of dicts: {"role": "user|assistant|other", "content": "..."}
    """
    memory = get_conversation_memory()
    try:
        messages = memory.get_messages(session_id)
    except Exception:
        # Fallback to empty list
        messages = []

    serialized = []
    try:
        from langchain_core.messages import HumanMessage, AIMessage
        for msg in messages:
            role = "other"
            if isinstance(msg, HumanMessage):
                role = "user"
            elif isinstance(msg, AIMessage):
                role = "assistant"

            serialized.append({
                "role": role,
                "content": getattr(msg, "content", "")
            })
    except Exception:
        # If langchain types not available, try to stringify messages
        for msg in messages:
            try:
                serialized.append({"role": "other", "content": str(msg)})
            except Exception:
                serialized.append({"role": "other", "content": ""})

    return serialized


def get_session_summary(session_id: str) -> str:
    """Wrapper for API expected `get_session_summary` name."""
    memory = get_conversation_memory()
    try:
        return memory.get_summary(session_id)
    except Exception:
        return ""


def clear_session(session_id: str) -> None:
    """Wrapper for API expected `clear_session` name."""
    memory = get_conversation_memory()
    try:
        memory.clear_history(session_id)
    except Exception:
        # best-effort
        pass
