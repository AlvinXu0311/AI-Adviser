"""
API endpoints for chat functionality with the LangGraph adviser agent.
The agent uses native tool calling for database-first knowledge retrieval.
Supports multi-turn conversation with memory management.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import logging
import asyncio
import json
import time
from asyncio import create_task
from ..schemas.chat import ChatRequest, ChatResponse
from ..services.context_manager import get_context_manager
from ..services.conversation_memory import (
    clear_session,
    generate_session_id,
    get_conversation_memory,
    get_history,
    get_session_summary,
)
from ..agents.adviser_agent import get_adviser_agent

logger = logging.getLogger(__name__)

router = APIRouter()

# Strong references to background compaction tasks so they are not garbage-collected mid-run
_background_tasks: set = set()


def _compact_in_background(memory, session_id: str) -> None:
    """Fold old turns into the Redis summary after the reply is out, off the request path."""
    task = create_task(memory.compact_if_needed(session_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def validate_query_basic_sanity(message: str) -> tuple[bool, str]:
    """
    Basic sanity check to prevent completely empty or garbage input.
    Does NOT reject multi-turn responses or short answers.

    Intent classification with Redis memory context will handle meaningfulness assessment.

    Returns:
        (is_valid, error_message): True if input is not garbage, False with error message if it is
    """
    msg = message.strip()

    # Check 1: Empty message
    if not msg:
        return False, "Message cannot be empty."

    # Check 2: Only special characters/punctuation (no alphanumeric)
    if not any(c.isalnum() for c in msg):
        return False, "Please provide a valid question or response."

    return True, ""


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    Process a chat message with the LangGraph adviser agent and stream the response.

    Flow:
    1. Generate or use existing session ID for conversation memory
    2. Store user message in conversation history
    3. Use agentic RAG (adviser agent) for autonomous tool-based reasoning
    4. Agent uses RAG retrieval and context lookup tools
    5. Stream intermediate steps (thoughts, actions) and final response
    6. Store assistant response in conversation history
    7. Return streaming response with source metadata and session ID

    Args:
        request: ChatRequest containing message, optional transcript context, and optional session_id

    Returns:
        StreamingResponse with generated message, response source, and session info
    """
    logger.info(f"Streaming chat request received: '{request.message[:50]}...'")
    started = time.perf_counter()
    
    async def stream_generator():
        queue = asyncio.Queue()

        async def agent_task():
            try:
                # Validate input
                logger.debug("Starting agent_task")
                if not request.message or len(request.message.strip()) == 0:
                    raise ValueError("Message cannot be empty")

                if len(request.message) > 5000:
                    raise ValueError("Message exceeds maximum length of 5000 characters")

                # Layer 1: Basic sanity check - only reject completely empty/garbage input
                logger.debug("Layer 1: Validating basic input sanity")
                is_valid, error_msg = validate_query_basic_sanity(request.message)
                if not is_valid:
                    logger.info(f"Query rejected at Layer 1 sanity check: '{request.message}'")
                    session_id = generate_session_id()
                    await queue.put(json.dumps({
                        "type": "final",
                        "content": error_msg,
                        "response_source": "input_validation",
                        "reasoning": "Input failed basic sanity check",
                        "tools_used": ["sanity_check"],
                        "intent": None,
                        "session_id": session_id,
                    }))
                    await queue.put(None)
                    return

                # Handle session ID and conversation memory
                logger.debug("Generating session ID")
                session_id = request.session_id or generate_session_id()
                
                # Set current session for tool access (contextvars)
                from ..services.context_manager import set_current_session
                set_current_session(session_id)
                logger.debug(f"Set current session: {session_id[:8]}...")
                
                logger.debug("Getting conversation memory")
                memory = get_conversation_memory()
                logger.debug("Adding user message to memory")
                memory.add_user_message(session_id, request.message)
                logger.debug("User message added successfully")

                # Get topic context
                logger.debug(f"Chat topic_id: {request.topic_id}")
                topic_id = request.topic_id  # 'general' or 'course'
                logger.info(f"User selected topic: {topic_id or 'not specified'}")

                # Get cached student context (session-based)
                logger.debug("Getting context manager")
                context_manager = get_context_manager()
                logger.debug(f"Getting student context for session: {session_id}")
                cached_context = context_manager.get_student_context(session_id)

                student_context_to_use = None
                if cached_context and cached_context.has_transcript():
                    student_context_to_use = cached_context
                elif request.transcript_context:
                    logger.debug("Building student context from transcript")
                    from ..schemas.transcript import ExtractedTranscriptData, ProgramInfo
                    student_context_to_use = ExtractedTranscriptData(
                        student_name=request.transcript_context.student_name,
                        student_id=request.transcript_context.student_name or "N/A",
                        gpa=request.transcript_context.gpa,
                        program_info=ProgramInfo(program_name=request.transcript_context.program) if request.transcript_context.program else None,
                        completed_courses=[],
                        current_courses=[]
                    )

                # Conversation context = compacted summary of older turns + recent turns verbatim
                logger.debug("Getting conversation history")
                conversation_history = get_history(session_id)
                conversation_summary = memory.get_compacted_summary(session_id)

                # Step 1: Intent Classification (with conversation history for context)
                logger.debug("Step 1: Classifying user intent")
                await queue.put(json.dumps({"type": "stage", "content": "Understanding your question"}))
                from ..agents.intent_agent import get_intent_agent
                intent_agent = get_intent_agent()
                intent_classification = await intent_agent.classify(
                    request.message, conversation_history, conversation_summary
                )
                logger.info(f"Intent detected: {intent_classification.intent} (confidence: {intent_classification.confidence}, is_academic: {intent_classification.is_academic})")

                # Layer 2: Intent validation - reject non-academic or low confidence queries
                logger.debug("Layer 2: Checking intent classification")
                CONFIDENCE_THRESHOLD = 0.2

                if not intent_classification.is_academic or intent_classification.confidence < CONFIDENCE_THRESHOLD:
                    logger.info(f"Query rejected at Layer 2: is_academic={intent_classification.is_academic}, confidence={intent_classification.confidence}")
                    response_text = ("I'm not sure how to help with that. Could you provide more context? "
                                   "For example: 'Tell me about MSIT program' or 'What are the requirements for specializations?'")

                    payload = {
                        "type": "final",
                        "content": response_text,
                        "response_source": "intent_classification",
                        "reasoning": f"Query not academic or low confidence (is_academic: {intent_classification.is_academic}, confidence: {intent_classification.confidence})",
                        "tools_used": ["intent_classification"],
                        "intent": intent_classification.model_dump() if intent_classification else None,
                        "session_id": session_id,
                    }
                    await queue.put(json.dumps(payload))
                    await queue.put(None)
                    return

                # Log confidence level for debugging
                logger.info(f"Intent classification passed. Proceeding to adviser agent.")

                # Step 2: Route to RAG Agent based on intent
                logger.debug("Step 2: Routing to RAG agent")
                await queue.put(json.dumps({"type": "stage", "content": "Planning which sources to check"}))
                adviser_agent = get_adviser_agent()

                async def forward_event(event: dict) -> None:
                    await queue.put(json.dumps(event))

                # Call RAG agent with intent context
                logger.debug("Step 3: Calling RAG agent with intent context")
                result = await adviser_agent.answer_query(
                    query=request.message,
                    context=student_context_to_use,
                    program_id="msit",  # Default program, could be parameterized
                    session_id=session_id,
                    conversation_history=conversation_history,
                    topic_id=topic_id,  # Pass selected topic
                    on_event=forward_event,
                    conversation_summary=conversation_summary,
                )

                response_text = result.get("response", "")
                logger.debug("RAG agent response generated")
                memory.add_ai_message(session_id, response_text)

                payload = {
                    "type": "final",
                    "content": response_text,
                    "response_source": result.get("source", "agentic_rag"),
                    "reasoning": result.get("reasoning", ""),
                    "tools_used": result.get("tools_used", []),
                    "intent": intent_classification.model_dump() if intent_classification else None,
                    "session_id": session_id,
                }
                await queue.put(json.dumps(payload))

                latency_ms = (time.perf_counter() - started) * 1000
                memory.record_latency(latency_ms)
                logger.info(f"Chat answered in {latency_ms:.0f} ms")
                _compact_in_background(memory, session_id)

            except Exception as e:
                logger.error(f"Error in agent task: {e}", exc_info=True)
                await queue.put(json.dumps({"type": "error", "content": str(e)}))
            finally:
                await queue.put(None)

        task = create_task(agent_task())

        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"data: {item}\n\n"
        
        await task

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.get("/chat/history/{session_id}")
async def get_conversation_history(session_id: str):
    """
    Retrieve conversation history for a given session ID.

    Args:
        session_id: The session ID to retrieve history for

    Returns:
        Dict containing conversation history and metadata
    """
    logger.info(f"Retrieving conversation history for session: {session_id}")

    try:
        history = get_history(session_id)

        return {
            "session_id": session_id,
            "message_count": len(history),
            "summary": get_session_summary(session_id),
            "compacted_summary": get_conversation_memory().get_compacted_summary(session_id),
            "messages": history
        }

    except Exception as e:
        logger.error(f"Error retrieving conversation history: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving history: {str(e)}")


@router.delete("/chat/history/{session_id}")
async def clear_conversation_history(session_id: str):
    """
    Clear conversation history for a given session ID.

    Args:
        session_id: The session ID to clear

    Returns:
        Success message
    """
    logger.info(f"Clearing conversation history for session: {session_id}")

    try:
        clear_session(session_id)

        return {
            "status": "success",
            "message": f"Conversation history cleared for session {session_id}"
        }

    except Exception as e:
        logger.error(f"Error clearing conversation history: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error clearing history: {str(e)}")


@router.get("/chat/memory/stats")
async def get_memory_stats():
    """
    Get memory management statistics.

    Returns:
        Dict with conversation memory stats
    """
    try:
        memory = get_conversation_memory()
        stats = memory.get_stats()
        return stats

    except Exception as e:
        logger.error(f"Error retrieving memory stats: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving stats: {str(e)}")