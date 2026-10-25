"""
API endpoints for chat functionality with the LangGraph adviser agent.
The agent uses native tool calling for database-first knowledge retrieval.
Supports multi-turn conversation with memory management.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import logging
import asyncio
import json
import os
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
from ..auth import User, get_current_user, require_admin
from ..observability import chat_turn_trace
from ..services.rate_limit import rate_limited
from ..services.session_access import claim_session, release_session, require_session_owner

logger = logging.getLogger(__name__)

router = APIRouter()

# Sent to the client instead of internal exception text (details stay in the server log)
GENERIC_ERROR = "Something went wrong while answering. Please try again."

TIMEOUT_ERROR = "This question took too long to answer. Please try again or ask something more specific."
ADVISER_TIMEOUT_SECONDS = float(os.getenv("ADVISER_TIMEOUT_SECONDS", "120"))

# SSE must not be buffered by nginx or cached by the browser
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

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


# Each chat turn costs several LLM calls: cap it per user per minute and per day
@router.post("/chat", response_model=ChatResponse,
             dependencies=[Depends(rate_limited("chat-day", "CHAT_RATE_LIMIT_PER_DAY", 300, 86400))])
async def chat(
    request: ChatRequest,
    user: User = Depends(rate_limited("chat-minute", "CHAT_RATE_LIMIT_PER_MINUTE", 10, 60)),
) -> StreamingResponse:
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
    logger.info(f"Streaming chat request received ({len(request.message)} chars)")
    started = time.perf_counter()

    # Bind the session to this user before streaming, so a foreign session id is a plain 403
    session_id = request.session_id or generate_session_id()
    await asyncio.to_thread(claim_session, session_id, user)
    
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
                    logger.info("Query rejected at Layer 1 sanity check")
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

                # Set current session for tool access (contextvars)
                from ..services.context_manager import set_current_session
                set_current_session(session_id)
                logger.debug(f"Set current session: {session_id[:8]}...")
                
                logger.debug("Getting conversation memory")
                memory = get_conversation_memory()
                logger.debug("Adding user message to memory")
                await asyncio.to_thread(memory.add_user_message, session_id, request.message)
                logger.debug("User message added successfully")

                # Get topic context
                logger.debug(f"Chat topic_id: {request.topic_id}")
                topic_id = request.topic_id  # 'general' or 'course'
                logger.info(f"User selected topic: {topic_id or 'not specified'}")

                # Get cached student context (session-based)
                logger.debug("Getting context manager")
                context_manager = get_context_manager()
                logger.debug(f"Getting student context for session: {session_id}")
                cached_context = await asyncio.to_thread(context_manager.get_student_context, session_id)

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
                conversation_history = await asyncio.to_thread(get_history, session_id)
                conversation_summary = await asyncio.to_thread(memory.get_compacted_summary, session_id)

                # One LangSmith trace per turn: intent + adviser graph nest under this root run
                trace_inputs = {"message": request.message, "topic": topic_id,
                                "has_transcript": student_context_to_use is not None}
                with chat_turn_trace(session_id, user.id, trace_inputs) as trace_run:
                    # Step 1: Intent Classification (with conversation history for context)
                    logger.debug("Step 1: Classifying user intent")
                    await queue.put(json.dumps({"type": "stage", "content": "Understanding your question"}))
                    from ..agents.intent_agent import classify_with_fallback
                    # Retries, then fails open instead of failing the whole request
                    intent_classification, intent_degraded = await classify_with_fallback(
                        request.message, conversation_history, conversation_summary
                    )
                    if trace_run and intent_degraded:
                        trace_run.add_tags(["intent-degraded"])
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
                        if trace_run:
                            trace_run.end(outputs={"response": response_text, "response_source": "intent_classification"})
                            payload["trace_id"] = str(trace_run.trace_id)
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
                    # Overall deadline for the agent loop (each LLM call also has its own timeout)
                    result = await asyncio.wait_for(adviser_agent.answer_query(
                        query=request.message,
                        context=student_context_to_use,
                        session_id=session_id,
                        conversation_history=conversation_history,
                        topic_id=topic_id,  # Pass selected topic
                        on_event=forward_event,
                        conversation_summary=conversation_summary,
                    ), timeout=ADVISER_TIMEOUT_SECONDS)

                    response_text = result.get("response", "")
                    logger.debug("RAG agent response generated")
                    await asyncio.to_thread(memory.add_ai_message, session_id, response_text)

                    payload = {
                        "type": "final",
                        "content": response_text,
                        "response_source": result.get("source", "agentic_rag"),
                        "reasoning": result.get("reasoning", ""),
                        "tools_used": result.get("tools_used", []),
                        "intent": intent_classification.model_dump() if intent_classification else None,
                        "session_id": session_id,
                    }
                    if trace_run:
                        trace_run.end(outputs={"response": response_text, "tools_used": payload["tools_used"],
                                               "response_source": payload["response_source"]})
                        # Lets a client attach feedback (thumbs up/down) to this trace later
                        payload["trace_id"] = str(trace_run.trace_id)
                    await queue.put(json.dumps(payload))

                latency_ms = (time.perf_counter() - started) * 1000
                await asyncio.to_thread(memory.record_latency, latency_ms)
                logger.info(f"Chat answered in {latency_ms:.0f} ms")
                _compact_in_background(memory, session_id)

            except asyncio.TimeoutError:
                logger.error(f"Adviser timed out after {ADVISER_TIMEOUT_SECONDS}s")
                await queue.put(json.dumps({"type": "error", "content": TIMEOUT_ERROR}))
            except asyncio.CancelledError:
                logger.info("Chat turn cancelled (client disconnected)")
                raise
            except Exception as e:
                logger.error(f"Error in agent task: {e}", exc_info=True)
                await queue.put(json.dumps({"type": "error", "content": GENERIC_ERROR}))
            finally:
                await queue.put(None)

        task = create_task(agent_task())

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {item}\n\n"
            await task
        finally:
            # Starlette cancels this generator when the client disconnects; stop the agent too,
            # so an abandoned turn doesn't keep spending LLM calls
            if not task.done():
                task.cancel()

    return StreamingResponse(stream_generator(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/chat/history/{session_id}")
async def get_conversation_history(session_id: str, user: User = Depends(get_current_user)):
    """
    Retrieve conversation history for a given session ID.

    Args:
        session_id: The session ID to retrieve history for

    Returns:
        Dict containing conversation history and metadata
    """
    await asyncio.to_thread(require_session_owner, session_id, user)
    logger.info(f"Retrieving conversation history for session: {session_id[:8]}...")

    def load() -> dict:
        history = get_history(session_id)
        return {
            "session_id": session_id,
            "message_count": len(history),
            "summary": get_session_summary(session_id),
            "compacted_summary": get_conversation_memory().get_compacted_summary(session_id),
            "messages": history
        }

    try:
        return await asyncio.to_thread(load)
    except Exception as e:
        logger.error(f"Error retrieving conversation history: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving history")


@router.delete("/chat/history/{session_id}")
async def clear_conversation_history(session_id: str, user: User = Depends(get_current_user)):
    """
    Clear conversation history for a given session ID.

    Args:
        session_id: The session ID to clear

    Returns:
        Success message
    """
    await asyncio.to_thread(require_session_owner, session_id, user)
    logger.info(f"Clearing conversation history for session: {session_id[:8]}...")

    def clear() -> None:
        clear_session(session_id)
        get_context_manager().clear_student_context(session_id)
        release_session(session_id)

    try:
        await asyncio.to_thread(clear)

        return {
            "status": "success",
            "message": f"Conversation history cleared for session {session_id}"
        }

    except Exception as e:
        logger.error(f"Error clearing conversation history: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error clearing history")


@router.get("/chat/memory/stats")
async def get_memory_stats(admin: User = Depends(require_admin)):
    """
    Get memory management statistics.

    Returns:
        Dict with conversation memory stats
    """
    try:
        return await asyncio.to_thread(get_conversation_memory().get_stats)

    except Exception as e:
        logger.error(f"Error retrieving memory stats: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving stats")