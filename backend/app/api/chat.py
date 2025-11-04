"""
API endpoints for chat functionality with LangChain agentic RAG.
Uses ReAct agent pattern with autonomous tool use for knowledge retrieval.
Supports multi-turn conversation with memory management.
"""
from fastapi import APIRouter, HTTPException
import logging
from ..schemas.chat import ChatRequest, ChatResponse, IntentType
from ..agents.adviser_agent import get_adviser_agent
from ..chains.rag_chain import get_rag_chain
from ..chains.chat_chain import get_chat_chain
from ..services.context_manager import get_context_manager
from ..services.conversation_memory import get_conversation_memory, generate_session_id
from ..utils.error_handler import handle_llm_error

logger = logging.getLogger(__name__)

router = APIRouter()

# Lazy initialization - services created on first request, not at module load
_adviser_agent = None
_rag_chain = None
_chat_chain = None


def get_agent():
    """Get or create AdviserAgent (lazy initialization)"""
    global _adviser_agent
    if _adviser_agent is None:
        _adviser_agent = get_adviser_agent()
    return _adviser_agent


def get_rag():
    """Get or create RAG chain (lazy initialization)"""
    global _rag_chain
    if _rag_chain is None:
        _rag_chain = get_rag_chain()
    return _rag_chain


def get_chat():
    """Get or create Chat chain (lazy initialization)"""
    global _chat_chain
    if _chat_chain is None:
        _chat_chain = get_chat_chain()
    return _chat_chain


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Process a chat message using LangChain agentic RAG with ReAct pattern.

    Flow:
    1. Generate or use existing session ID for conversation memory
    2. Store user message in conversation history
    3. Use agentic RAG (adviser agent) for autonomous tool-based reasoning
    4. Agent uses RAG retrieval and context lookup tools
    5. Store assistant response in conversation history
    6. Return response with source metadata and session ID

    Args:
        request: ChatRequest containing message, optional transcript context, and optional session_id

    Returns:
        ChatResponse with generated message, response source, and session info
    """
    logger.info(f"Chat request received via LangChain: '{request.message[:50]}...'")

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

        # Handle session ID and conversation memory
        session_id = request.session_id or generate_session_id()
        memory = get_conversation_memory()
        memory.add_user_message(session_id, request.message)
        logger.info(f"Session: {session_id}, stored user message")

        # Get cached student context from ContextManager (full transcript data from PDF)
        context_manager = get_context_manager()
        cached_context = context_manager.get_student_context()

        # Determine which context to use: cached (from PDF) or request context (from API)
        student_context_to_use = None
        context_source = "none"

        if cached_context:
            # Use full cached context from PDF extraction (has student_id, courses, grades, etc.)
            logger.info("Using complete cached student context from PDF extraction")
            logger.info(f"Cached context: {cached_context.student_name}, ID: {cached_context.student_id}, GPA: {cached_context.gpa}")
            logger.info(f"Completed courses: {len(cached_context.completed_courses) if cached_context.completed_courses else 0}")
            logger.info(f"Current courses: {len(cached_context.current_courses) if cached_context.current_courses else 0}")
            student_context_to_use = cached_context
            context_source = "cached_pdf"
        elif request.transcript_context:
            # Use request context if no cached context
            logger.info("Using student context from API request")
            # Convert to ExtractedTranscriptData for consistency
            from ..schemas.transcript import ExtractedTranscriptData, ProgramInfo
            student_context_to_use = ExtractedTranscriptData(
                student_name=request.transcript_context.student_name,
                student_id=request.transcript_context.student_name or "N/A",  # Fallback
                gpa=request.transcript_context.gpa,
                program_info=ProgramInfo(program_name=request.transcript_context.program) if request.transcript_context.program else None,
                completed_courses=[],
                current_courses=[]
            )
            context_source = "api_request"
        else:
            logger.info("No student context available (PDF not uploaded, no context in request)")
            context_source = "none"

        # Use LangChain agentic RAG for response
        logger.info(f"Processing with LangChain agentic RAG (ReAct agent), context_source={context_source}")

        agent = get_agent()
        result = await agent.answer_query(
            query=request.message,
            context=student_context_to_use,
            program_id="msit"
        )

        response_text = result.get("response", "")
        response_source = result.get("source", "agentic_rag")

        # Store assistant response in conversation memory
        memory.add_ai_message(session_id, response_text)
        logger.info(f"Session: {session_id}, stored assistant response")

        # Create a default intent classification for response
        from ..schemas.chat import IntentClassification
        intent_classification = IntentClassification(
            intent=IntentType.GENERAL_ACADEMIC,
            confidence=0.85,
            requires_transcript=request.transcript_context is not None,
            rule_applicable=False,
            suggested_response_type="llm"
        )

        logger.info(f"LangChain response generated: {len(response_text)} chars, source: {response_source}")

        # Return response with session ID for client to use in follow-up messages
        response = ChatResponse(
            response=response_text,
            intent=intent_classification,
            response_source=response_source
        )

        # Store session_id in response metadata by adding custom header
        logger.debug(f"Returning response with session_id: {session_id}")
        return response

    except ValueError as e:
        error_detail = f"Validation error: {str(e)}"
        logger.error(f"Validation error: {error_detail}")
        raise HTTPException(status_code=400, detail=error_detail)
    except Exception as e:
        logger.error(f"Unexpected error in chat endpoint: {str(e)}", exc_info=True)
        http_exception = handle_llm_error(e)
        raise http_exception


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
        memory = get_conversation_memory()
        history = memory.get_history(session_id)
        summary = memory.get_session_summary(session_id)

        return {
            "session_id": session_id,
            "message_count": len(history),
            "summary": summary,
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
        memory = get_conversation_memory()
        memory.clear_session(session_id)

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