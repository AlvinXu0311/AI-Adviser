"""
API endpoints for chat functionality with LangChain agentic RAG.
Uses ReAct agent pattern with autonomous tool use for knowledge retrieval.
Supports multi-turn conversation with memory management.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import logging
import asyncio
import json
from asyncio import create_task
from ..schemas.chat import ChatRequest, ChatResponse
from ..services.context_manager import get_context_manager
from ..services.conversation_memory import get_conversation_memory, generate_session_id
from ..agents.adviser_agent import get_adviser_agent
from langchain.callbacks.base import AsyncCallbackHandler

logger = logging.getLogger(__name__)

router = APIRouter()

_adviser_agent = None


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


def get_agent():
    global _adviser_agent
    if _adviser_agent is None:
        _adviser_agent = get_adviser_agent()
    return _adviser_agent


FINAL_ANSWER_MARKER = "Final Answer:"


def extract_thought(log: str) -> str:
    """Pull the reasoning text out of a ReAct log ("Thought: ... Action: ..." / "... Final Answer: ...")."""
    if not log:
        return ""
    text = log
    for marker in ("\nAction:", "Action:", FINAL_ANSWER_MARKER):
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    text = text.strip()
    if text.lower().startswith("thought:"):
        text = text[len("thought:"):].strip()
    return text


class StreamingCallbackHandler(AsyncCallbackHandler):
    """Custom callback handler for streaming agent output"""

    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        # Per-LLM-call buffer, used to stream only the text after "Final Answer:"
        self._llm_buffer = ""
        self._in_final_answer = False

    async def on_llm_start(self, serialized, prompts, **kwargs) -> None:
        self._llm_buffer = ""
        self._in_final_answer = False

    async def on_chat_model_start(self, serialized, messages, **kwargs) -> None:
        self._llm_buffer = ""
        self._in_final_answer = False

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        """Stream the final answer token by token; Thought/Action text is sent via agent_action instead."""
        if not token:
            return
        if self._in_final_answer:
            await self.queue.put(json.dumps({"type": "token", "content": token}))
            return
        self._llm_buffer += token
        idx = self._llm_buffer.find(FINAL_ANSWER_MARKER)
        if idx != -1:
            self._in_final_answer = True
            remainder = self._llm_buffer[idx + len(FINAL_ANSWER_MARKER):].lstrip()
            if remainder:
                await self.queue.put(json.dumps({"type": "token", "content": remainder}))

    async def on_agent_action(self, action, **kwargs) -> None:
        """Called when agent takes an action (uses a tool)"""
        logger.debug(f"Agent action: {action.tool}")
        if action.tool == "_Exception":
            return  # internal parsing-error recovery, not useful to the user
        await self.queue.put(json.dumps({
            "type": "agent_action",
            "tool": action.tool,
            "input": str(action.tool_input),
            "thought": extract_thought(action.log),
        }))

    async def on_agent_finish(self, finish, **kwargs) -> None:
        """Called when the agent produces its Final Answer"""
        await self.queue.put(json.dumps({
            "type": "agent_finish",
            "thought": extract_thought(finish.log),
        }))

    async def on_tool_start(self, serialized, input_str, **kwargs) -> None:
        """Called when a tool starts"""
        tool_name = serialized.get("name", "unknown")
        if tool_name == "_Exception":
            return
        logger.debug(f"Tool started: {tool_name}")
        await self.queue.put(json.dumps({
            "type": "tool_start",
            "tool_name": tool_name,
            "input": input_str
        }))

    async def on_tool_end(self, output, **kwargs) -> None:
        """Called when a tool ends"""
        if kwargs.get("name") == "_Exception":
            return
        logger.debug(f"Tool ended with output: {str(output)[:100]}")
        await self.queue.put(json.dumps({
            "type": "tool_end",
            "output": str(output)[:500]  # Limit output length
        }))


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

                # Get conversation history for context
                logger.debug("Getting conversation history")
                from ..services.conversation_memory import get_history as get_conversation_history
                conversation_history = get_conversation_history(session_id)

                # Step 1: Intent Classification (with conversation history for context)
                logger.debug("Step 1: Classifying user intent")
                await queue.put(json.dumps({"type": "stage", "content": "Understanding your question"}))
                from ..agents.intent_agent import get_intent_agent
                intent_agent = get_intent_agent()
                intent_classification = await intent_agent.classify(request.message, conversation_history)
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
                adviser_agent = get_agent()
                streaming_callback = StreamingCallbackHandler(queue)

                # Call RAG agent with intent context
                logger.debug("Step 3: Calling RAG agent with intent context")
                result = await adviser_agent.answer_query(
                    query=request.message,
                    context=student_context_to_use,
                    program_id="msit",  # Default program, could be parameterized
                    callbacks=[streaming_callback],
                    session_id=session_id,
                    conversation_history=conversation_history,
                    topic_id=topic_id  # Pass selected topic
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