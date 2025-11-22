"""
API endpoints for chat functionality with LangChain agentic RAG.
Uses ReAct agent pattern with autonomous tool use for knowledge retrieval.
Supports multi-turn conversation with memory management.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import logging
import asyncio
from asyncio import create_task
from ..schemas.chat import ChatRequest, ChatResponse, IntentType
from ..agents.adviser_agent import get_adviser_agent
from ..chains.rag_chain import get_rag_chain
from ..chains.chat_chain import get_chat_chain
from ..services.context_manager import get_context_manager
from ..services.conversation_memory import get_conversation_memory, generate_session_id
from ..utils.error_handler import handle_llm_error
from ..agents.streaming_callback import StreamingCallbackHandler

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
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    Process a chat message using LangChain agentic RAG with ReAct pattern and stream the response.

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
    
    async def stream_generator():
        queue = asyncio.Queue()
        handler = StreamingCallbackHandler(queue)

        async def agent_task():
            try:
                # Validate input
                if not request.message or len(request.message.strip()) == 0:
                    raise ValueError("Message cannot be empty")

                if len(request.message) > 5000:
                    raise ValueError("Message exceeds maximum length of 5000 characters")

                # Handle session ID and conversation memory
                session_id = request.session_id or generate_session_id()
                memory = get_conversation_memory()
                memory.add_user_message(session_id, request.message)

                # Get cached student context
                context_manager = get_context_manager()
                cached_context = context_manager.get_student_context()

                student_context_to_use = None
                if cached_context:
                    student_context_to_use = cached_context
                elif request.transcript_context:
                    from ..schemas.transcript import ExtractedTranscriptData, ProgramInfo
                    student_context_to_use = ExtractedTranscriptData(
                        student_name=request.transcript_context.student_name,
                        student_id=request.transcript_context.student_name or "N/A",
                        gpa=request.transcript_context.gpa,
                        program_info=ProgramInfo(program_name=request.transcript_context.program) if request.transcript_context.program else None,
                        completed_courses=[],
                        current_courses=[]
                    )

                # Get conversation history for context
                conversation_history = memory.get_messages(session_id)
                # Convert to dict format for agent
                history_dicts = []
                from langchain_core.messages import HumanMessage, AIMessage
                for msg in conversation_history:
                    if isinstance(msg, HumanMessage):
                        history_dicts.append({"role": "user", "content": msg.content})
                    elif isinstance(msg, AIMessage):
                        history_dicts.append({"role": "assistant", "content": msg.content})

                agent = get_agent()
                result = await agent.answer_query(
                    query=request.message,
                    context=student_context_to_use,
                    program_id="msit",
                    callbacks=[handler],
                    session_id=session_id,
                    conversation_history=history_dicts
                )
                
                response_text = result.get("response", "")
                memory.add_ai_message(session_id, response_text)

            except Exception as e:
                logger.error(f"Error in agent task: {e}", exc_info=True)
                await queue.put(f"data: {{\"type\": \"error\", \"content\": \"{str(e)}\"}}\n\n")
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