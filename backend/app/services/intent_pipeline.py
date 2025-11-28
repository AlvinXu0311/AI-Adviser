"""Intent → DB → templated response pipeline for chat endpoint."""
from __future__ import annotations

from typing import Any, Optional
import logging

from ..schemas.chat import IntentClassification, IntentType
from ..agents.intent_agent import get_intent_agent
from .program_db_service import get_program_db_service
from .response_templates import (
    program_response,
    academic_progress_response,
    clarify_response,
)

logger = logging.getLogger(__name__)

class IntentPipelineResult(dict):
    """Typed dict-like object containing response payload."""

    @property
    def response(self) -> str:
        return self.get("response", "")

    @property
    def intent(self) -> Optional[IntentClassification]:
        return self.get("intent")

    @property
    def response_source(self) -> str:
        return self.get("response_source", "system")


class IntentPipeline:
    """Coordinates intent detection, DB lookup, and templated responses."""

    def __init__(self) -> None:
        self.intent_agent = get_intent_agent()
        self.program_db = get_program_db_service()

    async def _classify(self, message: str) -> IntentClassification:
        try:
            return await self.intent_agent.classify(message)
        except Exception as exc:
            logger.error("Intent agent failed; returning generic intent: %s", exc)
            return IntentClassification(
                intent=IntentType.GENERAL_ACADEMIC,
                confidence=0.0,
                secondary_intents=[],
                requires_transcript=False,
                rule_applicable=False,
                suggested_response_type="clarify",
            )

    async def generate_response(
        self,
        message: str,
        student_context: Optional[Any] = None
    ) -> IntentPipelineResult:
        classification = await self._classify(message)
        intent = classification.intent

        if intent in {
            IntentType.PROGRAM_REQUIREMENTS,
            IntentType.COURSE_SELECTION,
            IntentType.PREREQUISITE,
            IntentType.GENERAL_ACADEMIC,
        }:
            snapshot = self.program_db.program_snapshot(message)
            response_text = program_response(snapshot, message)
            source = "business_school_database"
        elif intent == IntentType.ACADEMIC_PROGRESS:
            response_text = academic_progress_response(student_context)
            source = "student_context" if student_context else "system"
        else:
            response_text = clarify_response(intent, message)
            source = "system"

        return IntentPipelineResult(
            response=response_text,
            intent=classification,
            response_source=source,
        )


_PIPELINE: IntentPipeline | None = None


def get_intent_pipeline() -> IntentPipeline:
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = IntentPipeline()
    return _PIPELINE
