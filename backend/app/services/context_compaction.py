"""
Redis chat-context compaction.

Each session keeps two things in Redis:
- message_store:{session_id}  recent turns, verbatim (RedisChatMessageHistory list; LPUSH, so
                               index 0 is the newest message and the tail is the oldest)
- chat_summary:{session_id}    rolling LLM summary of every turn trimmed off that list

After a reply has been streamed, maybe_compact() checks the verbatim window. Once it holds more
than COMPACTION_TRIGGER_MESSAGES messages or about COMPACTION_TRIGGER_TOKENS tokens, the oldest
messages (all but the newest COMPACTION_KEEP_RECENT) are folded into the summary and trimmed from
the list in one MULTI/EXEC. The prompt each turn is then summary + recent window, so its size
stays flat however long the chat runs, and the summarization never sits on the request path.
"""
import json
import logging
import os
from typing import List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, messages_from_dict

from ..llm import get_chat_model

logger = logging.getLogger(__name__)

TRIGGER_MESSAGES = int(os.getenv("COMPACTION_TRIGGER_MESSAGES", 16))
TRIGGER_TOKENS = int(os.getenv("COMPACTION_TRIGGER_TOKENS", 6000))
KEEP_RECENT = int(os.getenv("COMPACTION_KEEP_RECENT", 6))
LOCK_SECONDS = 60

COMPACTION_PROMPT = """You maintain the running memory of a conversation between a WPI Business School \
student and their academic adviser assistant. Merge the earlier summary with the new turns into one \
updated summary.

Keep, as short bullet points:
- Facts about the student: program, specialization, completed or planned courses, GPA, goals, constraints
- Questions the student asked and the key facts given in answers (course codes, credits, requirements)
- Decisions made, recommendations given, and questions still open
Drop greetings, filler and repeated content. Never invent facts. At most 250 words.

EARLIER SUMMARY:
{summary}

NEW TURNS:
{turns}

UPDATED SUMMARY:"""


def message_key(session_id: str) -> str:
    return f"message_store:{session_id}"


def summary_key(session_id: str) -> str:
    return f"chat_summary:{session_id}"


def _lock_key(session_id: str) -> str:
    return f"chat_compaction_lock:{session_id}"


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 characters per token), good enough for a trigger threshold."""
    return len(text) // 4


def _text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)


def format_turns(messages: List[BaseMessage]) -> str:
    lines = []
    for message in messages:
        role = "Student" if isinstance(message, HumanMessage) else "Adviser"
        lines.append(f"{role}: {_text(message)}")
    return "\n\n".join(lines)


def split_for_compaction(messages: List[BaseMessage], keep_recent: int) -> int:
    """
    Number of oldest messages (chronological order) to fold into the summary.
    The verbatim window keeps the newest keep_recent messages and always starts on a student turn,
    so an adviser reply is never separated from the question it answers.
    """
    cut = max(len(messages) - keep_recent, 0)
    while cut < len(messages) and not isinstance(messages[cut], HumanMessage):
        cut += 1
    return cut


class ContextCompactor:
    """Folds old turns of a Redis-stored chat into a rolling summary."""

    def __init__(self, redis_client, session_ttl: int, llm=None):
        self.redis = redis_client
        self.session_ttl = session_ttl
        self._llm = llm  # built lazily so importing this module needs no API key

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_chat_model("compaction")
        return self._llm

    def get_summary(self, session_id: str) -> str:
        return self.redis.get(summary_key(session_id)) or ""

    def _load_messages(self, session_id: str) -> List[BaseMessage]:
        """Verbatim window in chronological order."""
        items = self.redis.lrange(message_key(session_id), 0, -1)
        return messages_from_dict([json.loads(item) for item in items[::-1]])

    def needs_compaction(self, messages: List[BaseMessage]) -> bool:
        if len(messages) <= KEEP_RECENT:
            return False
        if len(messages) > TRIGGER_MESSAGES:
            return True
        return estimate_tokens(format_turns(messages)) > TRIGGER_TOKENS

    async def maybe_compact(self, session_id: str) -> bool:
        """Compact the session if it is over threshold. Returns True if a compaction happened."""
        messages = self._load_messages(session_id)
        if not self.needs_compaction(messages):
            return False

        # One compaction per session at a time; a concurrent request just skips
        if not self.redis.set(_lock_key(session_id), "1", nx=True, ex=LOCK_SECONDS):
            logger.debug("Compaction already running for session %s", session_id[:8])
            return False
        try:
            # Re-read under the lock: another worker may have compacted in between
            messages = self._load_messages(session_id)
            cut = split_for_compaction(messages, KEEP_RECENT)
            if cut == 0 or not self.needs_compaction(messages):
                return False

            old_summary = self.get_summary(session_id)
            summary = await self._summarize(old_summary, messages[:cut])
            if not summary:
                logger.warning("Compaction for session %s returned an empty summary; skipped", session_id[:8])
                return False

            # New messages are LPUSHed onto the head while we summarize, so trimming `cut`
            # entries off the tail removes exactly the messages that were summarized.
            pipe = self.redis.pipeline(transaction=True)
            pipe.set(summary_key(session_id), summary, ex=self.session_ttl)
            pipe.ltrim(message_key(session_id), 0, -(cut + 1))
            pipe.expire(message_key(session_id), self.session_ttl)
            pipe.execute()

            before = estimate_tokens(old_summary + format_turns(messages))
            after = estimate_tokens(summary + format_turns(messages[cut:]))
            logger.info(
                "Compacted session %s: folded %d messages, kept %d, context ~%d → ~%d tokens",
                session_id[:8], cut, len(messages) - cut, before, after,
            )
            return True
        finally:
            self.redis.delete(_lock_key(session_id))

    async def _summarize(self, old_summary: str, messages: List[BaseMessage]) -> str:
        prompt = COMPACTION_PROMPT.format(
            summary=old_summary or "(none yet)",
            turns=format_turns(messages),
        )
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return _text(response).strip()


def summary_preamble(summary: Optional[str]) -> str:
    """Text appended to a system prompt so the model sees the compacted part of the chat."""
    if not summary:
        return ""
    return (
        "\n\n================================================================================\n"
        "EARLIER CONVERSATION (compacted summary of turns no longer shown verbatim)\n"
        "================================================================================\n"
        f"{summary}"
    )
