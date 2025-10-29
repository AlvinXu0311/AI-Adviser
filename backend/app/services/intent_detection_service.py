"""
Intent Detection Service using configurable LLM providers

This service classifies user questions into specific intents to enable:
1. Intelligent routing to appropriate handlers
2. Rule-based vs LLM-based response selection
3. Context awareness (transcript data requirement detection)

Supports multiple LLM providers: Google Gemini or Local Llama
"""

import json
import logging
import asyncio
import os
from typing import Optional
from app.schemas.chat import IntentType, IntentClassification, TranscriptContext

logger = logging.getLogger(__name__)


class IntentDetectionService:
    """Service for detecting and classifying user intent using configured LLM provider"""

    def __init__(self):
        """Initialize the intent detection service with configured provider"""
        self.provider = os.getenv("LLM_PROVIDER", "google").lower()

        if self.provider == "llama":
            from .llama_service import get_llama_service
            self.llm_backend = get_llama_service()
            print(f"[INFO] [Intent Detection] Using Llama provider")
        elif self.provider == "google":
            import google.generativeai as genai
            self.llm_backend = genai.GenerativeModel('gemini-2.5-flash')
            print(f"[INFO] [Intent Detection] Using Google Gemini provider")
        else:
            raise ValueError(f"Unknown LLM_PROVIDER: {self.provider}. Use 'google' or 'llama'")
        self.intent_prompt_template = """
You are an expert intent classifier for an academic advisor chatbot.

Analyze the following student question and classify its intent.

INTENT TYPES (choose the most relevant):
- course_selection: Questions about which courses to take, recommendations based on goals
- program_requirements: Questions about degree requirements, program structure, credits needed
- academic_progress: Questions about progress toward degree, completed courses, major requirements
- career_advice: Questions about career paths, job prospects, interview prep
- prerequisite: Questions about course prerequisites, prerequisites checking
- gpa_related: Questions about GPA, academic standing, grade improvements
- schedule_planning: Questions about course scheduling, time management, workload
- general_academic: General academic questions that don't fit other categories
- other: Questions completely unrelated to academics

RESPONSE FORMAT (JSON):
{{
    "intent": "one of the above intent types",
    "confidence": 0.0-1.0 confidence score,
    "secondary_intents": ["list of secondary intents if any"],
    "requires_transcript": true/false - does this query need student's transcript data?,
    "rule_applicable": true/false - can this be answered with rule-based logic?,
    "suggested_response_type": "llm" or "rule_based" or "hybrid"
}}

STUDENT QUESTION:
{question}

STUDENT CONTEXT (if available):
{context_info}

Respond ONLY with valid JSON, no additional text.
"""

    async def detect_intent(
        self,
        question: str,
        context: Optional[TranscriptContext] = None
    ) -> IntentClassification:
        """
        Detect and classify the intent of a user question.

        Args:
            question: The user's question
            context: Optional student transcript context

        Returns:
            IntentClassification object with detected intent details

        Raises:
            ValueError: If intent detection fails
        """
        logger.debug(f"Intent detection started for question: '{question[:50]}...'")
        try:
            # Build context info string
            context_info = self._build_context_string(context)
            logger.debug(f"Context: {context_info}")

            # Format the prompt with question and context
            prompt = self.intent_prompt_template.format(
                question=question,
                context_info=context_info
            )
            logger.debug("Prompt formatted successfully")

            # Get response from LLM provider (run in executor to avoid blocking)
            logger.debug(f"Calling {self.provider.upper()} API for intent detection...")
            loop = asyncio.get_running_loop()

            if self.provider == "google":
                # Google Gemini API
                response = await loop.run_in_executor(
                    None,
                    self.llm_backend.generate_content,
                    prompt
                )
                logger.debug("Gemini API call completed")
                response_text = response.text if hasattr(response, 'text') else response
            elif self.provider == "llama":
                # Llama via local service
                response_text = await self.llm_backend.generate_response(prompt)
                logger.debug("Llama API call completed")
            else:
                raise ValueError(f"Unknown provider: {self.provider}")

            if not response_text:
                raise ValueError("Empty response from intent detection model")

            logger.debug(f"LLM response received: {response_text[:100]}...")

            # Parse the JSON response
            intent_data = self._parse_intent_response(response_text)

            # Convert to IntentClassification object
            classification = IntentClassification(
                intent=IntentType(intent_data.get("intent", "other")),
                confidence=float(intent_data.get("confidence", 0.5)),
                secondary_intents=[
                    IntentType(i) for i in intent_data.get("secondary_intents", [])
                ],
                requires_transcript=bool(intent_data.get("requires_transcript", False)),
                rule_applicable=bool(intent_data.get("rule_applicable", False)),
                suggested_response_type=intent_data.get("suggested_response_type", "llm")
            )

            logger.info(f"Intent detected: {classification.intent} (confidence: {classification.confidence})")
            return classification

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse intent response JSON: {str(e)}")
            raise ValueError(f"Intent detection failed: Invalid response format")
        except ValueError as e:
            logger.error(f"Intent detection error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in intent detection: {str(e)}")
            raise ValueError(f"Intent detection failed: {str(e)}")

    def _build_context_string(self, context: Optional[TranscriptContext]) -> str:
        """Build a human-readable context string from transcript data"""
        if not context:
            return "No student context available"

        context_parts = []

        if context.student_name:
            context_parts.append(f"Name: {context.student_name}")
        if context.gpa is not None:
            context_parts.append(f"GPA: {context.gpa:.2f}/4.0")
        if context.program:
            context_parts.append(f"Program: {context.program}")
        if context.course_count is not None:
            context_parts.append(f"Courses Completed: {context.course_count}")

        return " | ".join(context_parts) if context_parts else "No student context available"

    def _parse_intent_response(self, response_text: str) -> dict:
        """
        Parse the JSON response from Gemini intent detection.

        Args:
            response_text: Raw response text from Gemini

        Returns:
            Dictionary with parsed intent data
        """
        try:
            # Try to extract JSON from the response
            # Handle cases where Gemini might add extra text
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")

            json_str = response_text[json_start:json_end]
            return json.loads(json_str)

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"JSON parsing error: {str(e)}")
            logger.error(f"Response text: {response_text}")
            # Return default intent on parsing failure
            return {
                "intent": "other",
                "confidence": 0.3,
                "secondary_intents": [],
                "requires_transcript": False,
                "rule_applicable": False,
                "suggested_response_type": "llm"
            }
