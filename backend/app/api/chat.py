"""
API endpoints for chat functionality with intelligent intent-based routing.
Uses shared context cache for efficient handling of PDF data.
"""
from fastapi import APIRouter, HTTPException
import google.generativeai as genai
import logging
from ..schemas.chat import ChatRequest, ChatResponse, IntentType
from ..services.llm_service import LLMService
from ..services.intent_detection_service import IntentDetectionService
from ..services.rule_based_response_service import RuleBasedResponseService
from ..services.context_manager import get_context_manager
from ..utils.error_handler import handle_llm_error

logger = logging.getLogger(__name__)

router = APIRouter()

# Lazy initialization - services created on first request, not at module load
# This ensures .env is fully loaded before services initialize
_llm_service = None
_intent_service = None
_rule_based_service = None


def get_llm_service():
    """Get or create LLMService (lazy initialization)"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


def get_intent_service():
    """Get or create IntentDetectionService (lazy initialization)"""
    global _intent_service
    if _intent_service is None:
        _intent_service = IntentDetectionService()
    return _intent_service


def get_rule_based_service():
    """Get or create RuleBasedResponseService (lazy initialization)"""
    global _rule_based_service
    if _rule_based_service is None:
        _rule_based_service = RuleBasedResponseService()
    return _rule_based_service


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Process a chat message with intelligent intent detection and routing.

    Flow:
    1. Detect user intent using Gemini LLM
    2. Route to rule-based system if applicable
    3. Otherwise use LLM with system prompt
    4. Return response with intent metadata

    Args:
        request: ChatRequest containing message and optional transcript context

    Returns:
        ChatResponse with generated message and intent classification
    """
    logger.info(f"Chat request received: '{request.message[:50]}...'")

    try:
        # Validate input
        if not request.message or len(request.message.strip()) == 0:
            error_msg = "Message cannot be empty"
            logger.warning(error_msg)
            raise ValueError(error_msg)

        if len(request.message) > 5000:
            error_msg = "Message exceeds maximum length of 5000 characters"
            logger.warning(error_msg)
            raise ValueError(error_msg)

        logger.debug(f"Input validation passed. Message length: {len(request.message)}")

        # Get cached student context from ContextManager
        context_manager = get_context_manager()
        cached_context = context_manager.get_student_context()

        # Use cached context if available, otherwise use request context
        if cached_context and not request.transcript_context:
            print("\n[Chat API] Using cached student context from PDF extraction")
            # Create a proper TranscriptContext object from cached data
            from ..schemas.chat import TranscriptContext
            request.transcript_context = TranscriptContext(
                student_name=cached_context.student_name,
                gpa=cached_context.gpa,
                program=cached_context.program_info.program_name if cached_context.program_info else None,
                course_count=(len(cached_context.completed_courses) if cached_context.completed_courses else 0) +
                             (len(cached_context.current_courses) if cached_context.current_courses else 0)
            )
            print(f"   Using: {cached_context.student_name} (GPA: {cached_context.gpa})")
        elif not request.transcript_context:
            print("\n[Chat API] No student context available (PDF not uploaded)")

        # Step 1: Detect intent using Gemini LLM
        logger.info("Step 1: Detecting intent with Gemini LLM...")
        try:
            intent_classification = await get_intent_service().detect_intent(
                question=request.message,
                context=request.transcript_context,
            )
            logger.info(f"✓ Intent detected: {intent_classification.intent.value} (confidence: {intent_classification.confidence:.2f})")
            logger.debug(f"  - Requires transcript: {intent_classification.requires_transcript}")
            logger.debug(f"  - Rule applicable: {intent_classification.rule_applicable}")
            logger.debug(f"  - Suggested type: {intent_classification.suggested_response_type}")
        except Exception as e:
            logger.error(f"✗ Intent detection failed: {str(e)}", exc_info=True)
            raise

        response_text = None
        response_source = "llm"

        # # Step 2: Try rule-based response if applicable
        # if intent_classification.rule_applicable and intent_classification.suggested_response_type in ["rule_based", "hybrid"]:
        #     logger.info("Step 2: Attempting rule-based response...")
        #     try:
        #         response_text = await rule_based_service.generate_response(
        #             intent=intent_classification.intent,
        #             question=request.message,
        #             context=request.transcript_context,
        #         )
        #         if response_text:
        #             response_source = "rule_based"
        #             logger.info(f"✓ Rule-based response generated (length: {len(response_text)} chars)")
        #         else:
        #             logger.info("Rule-based response returned None, will fall back to LLM")
        #     except Exception as e:
        #         logger.warning(f"⚠ Rule-based generation failed: {str(e)}", exc_info=True)
        #         logger.info("Will fall back to LLM")
        # else:
        #     logger.info("Step 2: Skipping rule-based (not applicable for this intent)")

        # Step 3: Fall back to LLM if no rule-based response
        if not response_text:
            logger.info("Step 3: Generating LLM response...")
            try:
                response_text = await get_llm_service().generate_response(
                    message=request.message,
                    context=request.transcript_context,
                )
                logger.info(f"✓ LLM response generated (length: {len(response_text)} chars)")
                if intent_classification.rule_applicable and response_source == "rule_based":
                    response_source = "hybrid"
                    logger.info("Response source: hybrid (rule + LLM)")
                else:
                    response_source = "llm"
                    logger.info("Response source: llm")
            except Exception as e:
                logger.error(f"✗ LLM response generation failed: {str(e)}", exc_info=True)
                raise

        # Return response with intent metadata
        logger.info(f"✓ Chat endpoint complete. Response source: {response_source}")
        return ChatResponse(
            response=response_text,
            intent=intent_classification,
            response_source=response_source
        )

    except ValueError as e:
        error_detail = f"Validation error: {str(e)}"
        logger.error(f"✗ {error_detail}")
        raise HTTPException(status_code=400, detail=error_detail)
    except Exception as e:
        logger.error(f"✗ Unexpected error in chat endpoint: {str(e)}", exc_info=True)
        http_exception = handle_llm_error(e)
        raise http_exception