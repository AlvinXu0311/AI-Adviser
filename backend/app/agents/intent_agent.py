"""LLM-powered intent classifier for the Business School adviser."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import List

from langchain_core.prompts import ChatPromptTemplate

from ..llm import get_chat_model
from ..schemas.chat import IntentClassification

logger = logging.getLogger(__name__)


INTENT_PROMPT_TEMPLATE = (
    "You are an intent classification agent for the WPI Business School chatbot.\n"
    "Analyze the user's query IN THE CONTEXT of the conversation history and determine:\n"
    "1. What they are asking about (free-form description)\n"
    "2. Whether it's a meaningful academic query\n"
    "3. Whether it requires their uploaded transcript data\n\n"
    "QUERY TYPES TO RECOGNIZE:\n"
    "- PERSONAL INFO: 'what do you know about me', 'my GPA', 'my courses', 'my progress', 'about me' → is_academic=true, requires_transcript=true, confidence=0.8-0.95\n"
    "- PROGRAM QUERIES: 'MSIT requirements', 'what programs', 'course info', 'specializations', 'MBA prerequisites' → is_academic=true, requires_transcript=false, confidence=0.7-0.95\n"
    "- ACADEMIC PLANNING: 'what should I take', 'recommend courses', 'my schedule' → is_academic=true, requires_transcript=true, confidence=0.7-0.9\n"
    "- CONVERSATION CONTEXT: 'what did we talk about', 'previous question', 'last topic', 'earlier discussion', 'what was that', 'you just said' → is_academic=true, requires_transcript=false, confidence=0.8-0.95\n"
    "- FOLLOW-UP QUESTIONS: 'tell me more', 'what else', 'can you explain', 'more details', 'yes', 'no', 'that one' → is_academic=true, requires_transcript=false, confidence=0.7-0.9\n"
    "- GREETINGS/TRIVIAL: 'hi', 'hello', 'test', random words (ONLY if no prior academic context) → is_academic=false, confidence=0.1-0.3\n\n"
    "CRITICAL RULES:\n"
    "1. If there is conversation history about academic topics, follow-up questions ARE academic (is_academic=true, confidence>=0.7)\n"
    "2. Questions like 'what did we talk about' or 'what was that' refer to previous academic discussion = is_academic=true\n"
    "3. Short responses like 'yes', 'MSBA', 'that one' in context of academic discussion = is_academic=true\n\n"
    "CONFIDENCE SCORING:\n"
    "- 0.8-1.0: Clear academic questions OR follow-ups to academic discussion\n"
    "- 0.5-0.8: General but valid academic queries\n"
    "- 0.2-0.5: Ambiguous but possibly academic\n"
    "- <0.2: Not academic AND no prior academic context\n\n"
    "Respond with ONLY valid JSON (no markdown, no backticks):\n"
    '{{ "intent": "free-form description of what user wants", "confidence": 0.0-1.0, "is_academic": true/false, "requires_transcript": true/false, "reasoning": "brief explanation" }}\n'
)


INTENT_PROMPT = INTENT_PROMPT_TEMPLATE


class IntentAgent:
    """Wraps the intent chat model (see app/llm.py) with a constrained JSON output."""

    def __init__(self) -> None:
        self.llm = get_chat_model("intent")
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", INTENT_PROMPT),
            ("human", "{context}Question: {question}"),
        ])
        self.chain = self.prompt | self.llm
        self.timeout = float(os.getenv("INTENT_AGENT_TIMEOUT", "6"))

    async def classify(
        self, message: str, conversation_history: list = None, conversation_summary: str = ""
    ) -> IntentClassification:
        logger.info("Intent agent classifying message: %s", message[:60])
        logger.debug("Intent agent timeout setting: %s seconds", self.timeout)
        
        # Build context from conversation history
        context = ""
        if conversation_summary:
            context = f"[EARLIER CONVERSATION SUMMARY]:\n{conversation_summary[:1500]}\n\n"
        if conversation_history and len(conversation_history) > 0:
            context_parts = ["[CONVERSATION HISTORY - use this to understand context]:"]
            for msg in conversation_history[-6:]:  # Last 6 messages (3 turns)
                role = msg.get('role', 'unknown').upper()
                content = msg.get('content', '')[:150]  # Truncate
                context_parts.append(f"{role}: {content}")
            context += "\n".join(context_parts) + "\n\n"
            logger.info(f"Intent classification with {len(conversation_history)} history messages")
        
        try:
            logger.debug("Invoking LLM chain for intent classification (using thread executor)")
            # to_thread (unlike run_in_executor) copies contextvars, so the LLM call nests
            # under the chat turn's LangSmith trace
            llm_output = await asyncio.wait_for(
                asyncio.to_thread(self._invoke_chain, message, context),
                timeout=self.timeout,
            )
            logger.debug("LLM chain invocation completed")
        except asyncio.TimeoutError as exc:
            logger.error("Intent agent timed out after %s seconds", self.timeout)
            raise TimeoutError("intent agent timeout") from exc
        except Exception as exc:
            logger.error("Intent agent invocation failed: %s", exc, exc_info=True)
            raise

        raw_text = self._extract_text(llm_output)
        logger.debug("Intent agent raw output: %s", raw_text)

        parsed = self._fallback_parse(raw_text)

        return IntentClassification(
            intent=str(parsed.get("intent", "unknown")),
            confidence=float(parsed.get("confidence", 0.5)),
            is_academic=self._to_bool(parsed.get("is_academic", True)),
            requires_transcript=self._to_bool(parsed.get("requires_transcript", False)),
            reasoning=str(parsed.get("reasoning", "")),
        )

    def _invoke_chain(self, message: str, context: str = ""):
        """Synchronous wrapper for chain invocation to ensure proper timeout handling."""
        logger.debug("_invoke_chain: calling self.chain.invoke with message and context")
        return self.chain.invoke({"question": message, "context": context})

    @staticmethod
    def _to_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "1"}
        return bool(value)

    @staticmethod
    def _extract_text(response) -> str:
        if isinstance(response, str):
            return response
        text_attr = getattr(response, "text", None)
        if isinstance(text_attr, str) and text_attr:
            return text_attr
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    value = part.get("text") or part.get("content")
                    if value:
                        parts.append(str(value))
                else:
                    candidate = getattr(part, "text", None)
                    if candidate:
                        parts.append(str(candidate))
                    else:
                        parts.append(str(part))
            return "".join(parts)
        return str(response)

    @staticmethod
    def _fallback_parse(raw_text: str) -> dict:
        cleaned = raw_text.strip()
        # Remove markdown code block markers
        if cleaned.startswith("```"):
            # Remove opening ```
            cleaned = cleaned[3:]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            # Remove closing ```
            cleaned = cleaned.rstrip("`")

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = cleaned[start:end+1]
        else:
            candidate = cleaned

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as e:
            logger.warning("Intent agent fallback JSON parse failed: %s; returning defaults", e)
            data = {}

        if not isinstance(data, dict):
            data = {}

        data.setdefault("intent", "unknown")
        data.setdefault("confidence", 0.5)
        data.setdefault("is_academic", True)
        data.setdefault("requires_transcript", False)
        data.setdefault("reasoning", "")
        return data

_INTENT_AGENT: IntentAgent | None = None


def get_intent_agent() -> IntentAgent:
    global _INTENT_AGENT
    if _INTENT_AGENT is None:
        _INTENT_AGENT = IntentAgent()
    return _INTENT_AGENT


INTENT_ATTEMPTS = int(os.getenv("INTENT_AGENT_ATTEMPTS", "2"))


async def classify_with_fallback(
    message: str, conversation_history: list = None, conversation_summary: str = ""
) -> tuple[IntentClassification, bool]:
    """
    Classify with retries; if every attempt fails (timeout, provider error), fail open.

    Failing open is safe here: the intent gate only saves cost on off-topic questions, and the
    adviser can only answer from read-only academic tools. Returns (classification, degraded).
    """
    agent = get_intent_agent()
    for attempt in range(1, INTENT_ATTEMPTS + 1):
        try:
            return await agent.classify(message, conversation_history, conversation_summary), False
        except Exception as exc:
            logger.warning("Intent classification attempt %d/%d failed: %s", attempt, INTENT_ATTEMPTS, exc)
    logger.error("Intent classifier unavailable; passing the question to the adviser")
    return IntentClassification(
        intent="unclassified",
        confidence=1.0,
        is_academic=True,
        requires_transcript=False,
        reasoning="Intent classifier unavailable; defaulted to academic",
    ), True
