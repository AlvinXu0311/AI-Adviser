"""
Adviser agent built as a LangGraph StateGraph with native tool calling
(Gemini by default, or the Qwen3 LoRA model; see app/llm.py).

Graph:
    START → agent ⇄ tools → END
The agent node calls the model with the tools bound; tools_condition routes to the
ToolNode while the model keeps requesting tools, and to END once it answers.
After MAX_TOOL_ROUNDS tool rounds the agent is called without tools so it must answer.
"""
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .tools import get_all_tools, business_school_db_tool
from ..llm import get_chat_model
from ..services.context_compaction import summary_preamble

logger = logging.getLogger(__name__)

# Max agent → tools round trips per question (the old AgentExecutor used max_iterations=10)
MAX_TOOL_ROUNDS = 8

# Async callback that receives SSE-ready event dicts while the graph runs
EventSink = Callable[[Dict[str, Any]], Awaitable[None]]


class AdviserState(MessagesState):
    """Graph state: the chat messages plus the compacted summary of older turns."""
    summary: str


def get_available_programs() -> List[str]:
    """
    Dynamically fetch available programs from the database.
    Returns a list of program names/codes that degree_progress supports.
    """
    try:
        from ..services.program_db_service import get_program_db_service
        db_service = get_program_db_service()
        programs = db_service.get_all_programs()

        if not programs:
            logger.warning("No programs found in database, using fallback list")
            return ["MSIT", "MSBA", "MBA", "MBA in Analytics", "FinTech", "MSOS"]

        # Extract unique program codes/names
        program_list = []
        for p in programs:
            code = p.get('program_code', '')
            name = p.get('program_name', '')
            # Create a readable format: "MSIT (Master's in Information Technology)"
            if code and name and code != name:
                program_list.append(f"{code} ({name})")
            elif name:
                program_list.append(name)
            elif code:
                program_list.append(code)

        logger.info(f"Loaded {len(program_list)} programs from database: {program_list}")
        return program_list
    except Exception as e:
        logger.error(f"Failed to fetch programs from database: {e}")
        return ["MSIT", "MSBA", "MBA", "MBA in Analytics", "FinTech", "MSOS"]


def get_program_list_for_prompt() -> str:
    """
    Get formatted program list for inclusion in agent prompt.
    Fetches dynamically from database.
    """
    programs = get_available_programs()
    if not programs:
        return "No programs available in database."

    # Format as bullet list
    return "\n".join(f"- {p}" for p in programs)


SYSTEM_PROMPT_TEMPLATE = """You are an expert Academic Adviser for WPI Business School.
You help students with program information, course planning, and academic guidance.

DATA SOURCES (all reached through your tools):
- Business School SQLite database: AUTHORITATIVE source
- PDF academic catalogs via semantic search: FALLBACK
- The student's uploaded transcript (if any)
All search tools are DB-first with RAG fallback and retry built in.

================================================================================
TOOL SELECTION
================================================================================
1. Course questions (who teaches, description, credits, prerequisites, topic search)
   → smart_course_search  (PRIMARY for courses)
2. Program questions (requirements, specializations, structure) → program_search
3. Degree progress ("what do I still need?", "am I close to graduating?")
   → degree_progress  (needs an uploaded transcript)
4. Personal info (GPA, completed / current courses) → student_context
5. Program structure overview straight from the database → business_school_database
6. Nothing found by the tools above → semantic_search, or pdf_context for long context

Use several tools for complex questions: comparisons (search each option separately),
course details after finding program requirements, study plans, "best"/"recommended"
questions. One tool is enough for a simple lookup. You may call independent tools in
parallel.

================================================================================
CONVERSATIONAL BEHAVIOR
================================================================================
Ask a clarifying question instead of assuming when:
- the user has not said which program they are in or interested in,
- they ask for course recommendations without context or goals,
- they ask "what should I take?" without background.
Never assume the user's program or career goals. If a transcript is uploaded, check
student_context first to see their program.

================================================================================
DEGREE PROGRESS (CRITICAL)
================================================================================
Before calling degree_progress:
1. Transcript: if none is uploaded, ask the student to upload it with the paperclip icon.
2. Program: if unclear, ask which program they are in and list the available programs.
   If the program is not in the list below, say it is not supported and list the ones that are.
3. Confirm the program back to the student when you run the check.

AVAILABLE PROGRAMS (from the database; degree_progress only works for these):
{program_list}

================================================================================
RULES
================================================================================
- Only use tool-provided data. Never invent course codes, credits, instructors or requirements.
- Cite your source: "According to the database..." or "Based on the catalog...".
- If all tools return nothing, say: "I don't have that information available".
- For personal questions without a transcript, suggest uploading a PDF transcript.
- Give a complete, well-organized answer in Markdown."""

FORCE_ANSWER_NOTE = (
    "[System note] Tool budget reached. Do not call any more tools; answer now using "
    "only the information gathered above, and say what you could not verify."
)


def _message_text(message: BaseMessage) -> str:
    """Visible answer text of a message or chunk (excludes thinking blocks)."""
    content = message.content
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


def _message_thinking(message: BaseMessage) -> str:
    """Gemini thought summary carried by a message, if thinking output was requested."""
    content = message.content
    if isinstance(content, str):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") in ("thinking", "reasoning"):
            parts.append(block.get("thinking") or block.get("reasoning") or "")
    return "\n".join(p for p in parts if p).strip()


def _tool_rounds_this_turn(messages: List[BaseMessage]) -> int:
    """Count agent tool-call rounds since the latest human message."""
    rounds = 0
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, AIMessage) and message.tool_calls:
            rounds += 1
    return rounds


def _history_to_messages(history: Optional[List[Dict[str, str]]], current_query: str) -> List[BaseMessage]:
    """Turn stored {role, content} history into chat messages, dropping the current query."""
    if not history:
        return []
    turns = history[-20:]
    # chat.py stores the user message before loading history, so the last entry is this query
    if turns and turns[-1].get("role") == "user" and turns[-1].get("content") == current_query:
        turns = turns[:-1]
    messages: List[BaseMessage] = []
    for msg in turns:
        content = msg.get("content") or ""
        if not content:
            continue
        if msg.get("role") == "user":
            messages.append(HumanMessage(content=content))
        elif msg.get("role") == "assistant":
            messages.append(AIMessage(content=content))
    return messages


class AdviserAgent:
    """
    Academic adviser agent on LangGraph.
    Database-First architecture: tools query SQLite first and fall back to the PDF catalogs.
    """

    def __init__(self):
        """Initialize the adviser agent with tools, language model, and compiled graph"""
        self.llm = get_chat_model("adviser")

        self.tools = get_all_tools()

        # Dynamically fetch available programs from database
        self.available_programs = get_available_programs()
        self.program_list_str = get_program_list_for_prompt()
        logger.info(f"Loaded available programs: {self.available_programs}")

        self.system_prompt = SYSTEM_PROMPT_TEMPLATE.format(program_list=self.program_list_str)
        self.graph = self._build_graph()

    def _build_graph(self):
        """Compile the agent ⇄ tools graph"""
        llm_with_tools = self.llm.bind_tools(self.tools)

        async def agent(state: AdviserState) -> Dict[str, Any]:
            system_message = SystemMessage(content=self.system_prompt + summary_preamble(state.get("summary")))
            messages = [system_message, *state["messages"]]
            if _tool_rounds_this_turn(state["messages"]) >= MAX_TOOL_ROUNDS:
                logger.warning("Tool budget reached; forcing a final answer")
                response = await self.llm.ainvoke([*messages, HumanMessage(content=FORCE_ANSWER_NOTE)])
            else:
                response = await llm_with_tools.ainvoke(messages)
            return {"messages": [response]}

        builder = StateGraph(AdviserState)
        builder.add_node("agent", agent)
        builder.add_node("tools", ToolNode(self.tools))
        builder.add_edge(START, "agent")
        builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
        builder.add_edge("tools", "agent")
        return builder.compile()

    async def answer_query(
        self,
        query: str,
        context: Optional[Any] = None,  # Can be ExtractedTranscriptData or TranscriptContext or StudentContext
        program_id: str = "msit",
        session_id: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        topic_id: Optional[str] = None,  # Selected advising topic: 'general' or 'course'
        on_event: Optional[EventSink] = None,
        conversation_summary: str = "",
    ) -> Dict[str, Any]:
        """
        Process a student query by running the agent graph.

        Args:
            query: Student's question
            context: Optional transcript context (StudentContext from session-based storage)
            program_id: Program identifier (msit, msba, msm)
            session_id: Session ID for context isolation
            conversation_history: Prior turns as {role, content} dicts
            topic_id: Selected advising topic
            on_event: Optional async sink for streaming events
                (token, agent_action, tool_start, tool_end, agent_finish)
            conversation_summary: Compacted summary of turns older than conversation_history

        Returns:
            Dict with response, reasoning, and tools used
        """
        try:
            logger.info(f"Processing query with adviser agent: {query[:50]}...")
            logger.info(f"Topic context: {topic_id or 'not specified'}")
            logger.info(f"Session ID: {session_id[:8] if session_id else 'None'}...")

            has_transcript = self._has_transcript(context)
            input_text = self._format_agent_input(
                self._with_db_prefetch(query), context, program_id, self._topic_guidance(topic_id)
            )
            messages = [*_history_to_messages(conversation_history, query), HumanMessage(content=input_text)]

            async def emit(event: Dict[str, Any]) -> None:
                if on_event:
                    await on_event(event)

            logger.info("Executing adviser graph...")
            final_message: Optional[AIMessage] = None
            tools_used: List[str] = []
            async for mode, chunk in self.graph.astream(
                {"messages": messages, "summary": conversation_summary},
                {"recursion_limit": 2 * MAX_TOOL_ROUNDS + 3},
                stream_mode=["messages", "updates"],
            ):
                if mode == "messages":
                    message_chunk, metadata = chunk
                    if metadata.get("langgraph_node") == "agent":
                        token = _message_text(message_chunk)
                        if token:
                            await emit({"type": "token", "content": token})
                    continue

                for node, update in chunk.items():
                    if not update:
                        continue
                    if node == "agent":
                        ai_message = update["messages"][-1]
                        thought = _message_thinking(ai_message)
                        if ai_message.tool_calls:
                            # Text the model wrote before calling tools is reasoning, not the answer
                            thought = thought or _message_text(ai_message).strip()
                            for i, call in enumerate(ai_message.tool_calls):
                                tools_used.append(call["name"])
                                tool_input = json.dumps(call["args"], ensure_ascii=False)
                                await emit({
                                    "type": "agent_action",
                                    "tool": call["name"],
                                    "input": tool_input,
                                    "thought": thought if i == 0 else "",
                                })
                                await emit({
                                    "type": "tool_start",
                                    "id": call["id"],
                                    "tool_name": call["name"],
                                    "input": tool_input,
                                })
                        else:
                            final_message = ai_message
                            await emit({"type": "agent_finish", "thought": thought})
                    elif node == "tools":
                        for tool_message in update["messages"]:
                            await emit({
                                "type": "tool_end",
                                "id": tool_message.tool_call_id,
                                "output": str(tool_message.content)[:500],
                            })

            response = _message_text(final_message).strip() if final_message else ""
            if not response:
                response = "I wasn't able to put together an answer for that. Could you rephrase the question?"

            # Add guidance if query seems to be about personal progress without context
            if self._is_personal_progress_query(query) and not context:
                response += "\n\n**Note:** For personalized academic planning based on your transcript, please upload your PDF transcript to access your complete information."
                logger.info("Added transcript upload guidance to response")

            logger.info(f"Agent response generated: {len(response)} chars, tools: {tools_used}")

            return {
                "response": response,
                "reasoning": "LangGraph adviser agent with native tool calling and database-first tools",
                "tools_used": list(dict.fromkeys(tools_used)),
                "source": "database_first",
                "has_transcript": has_transcript,
            }

        except Exception as e:
            logger.error(f"Error in adviser agent: {str(e)}", exc_info=True)
            raise ValueError(f"Agent processing failed: {str(e)}")

    @staticmethod
    def _topic_guidance(topic_id: Optional[str]) -> str:
        if topic_id == "general":
            return "[CONTEXT] User selected: General Advising - Focus on program overview, policies, degree requirements, specialization options."
        if topic_id == "course":
            return "[CONTEXT] User selected: Courses & Planning - Focus on course schedules, catalog details, prerequisites, course selection."
        return ""

    @staticmethod
    def _with_db_prefetch(query: str) -> str:
        """Attach the database summary to program/course questions so answers start from authoritative data."""
        query_lower = query.lower()
        program_keywords = ['msit', 'msba', 'msm', 'course', 'requirement', 'specialization',
                            'graduation', 'prerequisite', 'program', 'core', 'degree', 'major']
        if not any(kw in query_lower for kw in program_keywords):
            return query

        logger.info("Detected program/course question - prefetching Business School database summary")
        try:
            db_summary = business_school_db_tool(query)
        except Exception as db_err:
            logger.error("Failed to fetch Business School database summary: %s", db_err)
            return query
        if not db_summary or not db_summary.strip():
            logger.info("Database returned no results for program question")
            return query
        logger.info("Business School database summary injected (%d chars)", len(db_summary))
        return f"{query}\n\n[Business School Database Information]:\n{db_summary}"

    @staticmethod
    def _has_transcript(context: Optional[Any]) -> bool:
        from ..services.context_manager import StudentContext
        if isinstance(context, StudentContext) and context.has_transcript():
            logger.info(f"Using StudentContext: student={context.student_name}, courses={len(context.courses)}")
            return True
        logger.info("No transcript context - user must upload PDF for personalized info")
        return False

    def _is_personal_progress_query(self, query: str) -> bool:
        """
        Detect if query is about personal academic progress/transcript.
        Returns True if user is asking about their own progress/path/tracking.
        """
        personal_keywords = [
            "my gpa", "my grade", "my progress", "my transcript", "my courses",
            "what did i", "have i taken", "should i", "can i", "my performance",
            "my standing", "my academic", "my plan", "my path", "my track",
            "how am i", "where am i", "tell me about me", "about my",
            "what courses have i", "which courses did i", "completed courses"
        ]
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in personal_keywords)

    def _format_agent_input(
        self,
        query: str,
        context: Optional[Any] = None,
        program_id: str = "msit",
        topic_guidance: str = ""
    ) -> str:
        """Format the current turn's input, handling StudentContext from session-based storage"""
        from ..services.context_manager import StudentContext

        input_text = ""

        if topic_guidance:
            input_text += topic_guidance + "\n"

        input_text += f"Student Question: {query}\n"

        if context and isinstance(context, StudentContext) and context.has_transcript():
            input_text += f"\nStudent Context:\n"
            if context.student_name:
                input_text += f"- Name: {context.student_name}\n"
            if context.student_id:
                input_text += f"- Student ID: {context.student_id}\n"
            if context.gpa is not None:
                input_text += f"- GPA: {context.gpa}/4.0\n"
            if context.degree_program:
                input_text += f"- Program: {context.degree_program}\n"

            # Count completed courses
            if context.courses:
                input_text += f"- Completed Courses: {len(context.courses)}\n"

        input_text += f"\nProgram: {program_id.upper()}"

        return input_text


# Singleton instance
_adviser_agent = None


def get_adviser_agent() -> AdviserAgent:
    """Get or create the adviser agent"""
    global _adviser_agent
    if _adviser_agent is None:
        _adviser_agent = AdviserAgent()
    return _adviser_agent
