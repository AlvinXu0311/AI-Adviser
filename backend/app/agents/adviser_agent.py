from typing import Optional, Any, Dict, List
from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.callbacks.base import AsyncCallbackHandler
import logging
import os

from ..schemas.chat import TranscriptContext
from .tools import get_all_tools, business_school_db_tool
from ..services.context_manager import get_context_manager

logger = logging.getLogger(__name__)


class AdviserAgent:
    """
    Chat Agent using LangChain's ReAct pattern for conversational advising.
    Database-First architecture with direct SQLite queries.
    Handles academic advising with autonomous decision-making and tool use.

    Architecture:
    - ReAct Pattern: Reasoning + Acting with tool use
    - Database-First: Direct SQLite queries via business_school_database tool
    - Tools: business_school_database, student_context, assess_complexity
    """

    def __init__(self):
        """Initialize the adviser agent with tools and language model"""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")

        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            temperature=0.3,  # Lower temperature for more consistent output format
            max_output_tokens=2048,
            google_api_key=api_key,
            streaming=True
        )

        # DEPRECATED: RAG Agent no longer used - Database-First architecture
        # from .rag_agent import get_rag_agent
        # self.rag_agent = get_rag_agent()

        self.tools = get_all_tools()

        # Improved system prompt for agentic reasoning
        self.system_prompt = """You are an expert Academic Adviser for WPI Business School.
    Your expertise: Programs (MSIT, MSBA, MSM), course requirements, specializations, student academic planning, and the official Business School SQLite database.

CORE RESPONSIBILITIES:
1. Answer student questions about degree programs, requirements, and courses
2. Help plan academic paths based on student background and goals
3. Provide guidance on specializations and elective options
4. Address questions about student transcripts and academic progress (if uploaded)

MANDATORY TOOL USAGE (ReAct Pattern):
You MUST use tools for every question. Here's what to do:

Program/Course Questions (MUST use business_school_database):
- "What is MSIT?" → Use business_school_database
- "What are the courses?" → Use business_school_database
- "What are requirements?" → Use business_school_database
- "What specializations?" → Use business_school_database

Personal Progress Questions (use student_context):
- "What's my GPA?" → Use student_context
- "What courses did I take?" → Use student_context

Complexity Assessment:
- When uncertain about query type → Use assess_complexity

CRITICAL RULES:
- NEVER answer "I don't have information" without using business_school_database first
- ONLY use tool-provided data - never invent course codes, credits, or requirements
- Always cite your source: "According to the Business School database..." or "Based on your transcript..."
- Be concise (2-3 sentences max unless detailed explanation needed)
- If tools return nothing, explicitly say: "I don't have that in the database"
- For personal questions without transcript: suggest uploading a PDF"""

        self.agent_executor = self._create_agent()

    def _create_agent(self) -> AgentExecutor:
        """Create the ReAct agent with optimized prompt for agentic reasoning"""
        prompt_template = """You are an expert Academic Adviser for WPI Business School.

SYSTEM CONTEXT:
You help students with program information, course planning, and academic guidance.
You have access to:
- Business School SQLite database (AUTHORITATIVE source for program/specialty/course information)
- Student transcript cache (if they uploaded their PDF)
- Assessment tools for query complexity

DATABASE-FIRST ARCHITECTURE:
The SQLite database is your PRIMARY and ONLY source for accurate program/course data.
All data queries MUST go through the business_school_database tool.

MANDATORY TOOL USAGE (ReAct Pattern - Database First):
You MUST use tools for EVERY question. Follow this process:

1. IDENTIFY QUESTION TYPE & RESOLVE PRONOUNS:
    - Always look at conversation history to understand pronouns like "they", "these", "those"
    - "program/course/specialization/requirement/graduation/prerequisite" → MUST use business_school_database FIRST
    - "my GPA/transcript/progress/grades/courses" + pronouns referring to courses → use student_context
    - "What are they?" / "Tell me more" in multi-turn → resolve from conversation history, then use appropriate tool
    - Anything uncertain → use assess_complexity then business_school_database

2. USE TOOLS (REQUIRED):
   For personal progress questions (GPA, completed courses, current courses):
   - ALWAYS call student_context to get actual student data
   Example: User asks "what courses have I completed?" or "what are they?"
   → You MUST respond: Action: student_context
                        Action Input: courses

   For program/database questions:
   - ALWAYS call business_school_database with the user's question
   Example: User says "What are MSIT requirements?"
   → You MUST respond: Action: business_school_database
                        Action Input: What are MSIT requirements?

3. RESPOND ONLY WITH TOOL DATA:
    - Quote course codes, credits, and specialization names directly from tool results
    - Always cite source: "According to your transcript..." or "According to the Business School database..."
    - If tools return nothing, explicitly say: "I don't have that information available"
    - Never answer from general knowledge about WPI

CRITICAL RULES (VIOLATIONS = WRONG ANSWER):
- If user asks about their personal courses → student_context is MANDATORY
- If user asks about programs/requirements → business_school_database is MANDATORY
- NEVER answer "I don't have information" without trying the appropriate tool first
- NEVER invent course codes, credits, or requirements
- Always cite your source when answering
- Resolve pronouns by looking at conversation history before taking action

You have access to the following tools:

{tools}

Tool names: {tool_names}

================================================================================
RESPONSE FORMAT (STRICTLY REQUIRED - NO EXCEPTIONS):
================================================================================

You MUST respond in ONE of these two formats ONLY:

FORMAT A - When you need to use a tool:
```
Thought: [your reasoning about what tool to use and why]
Action: [exactly one tool name from: {tool_names}]
Action Input: [the input string for the tool]
```

FORMAT B - When you have the final answer (ONLY after getting tool results):
```
Thought: I now have the information needed to answer the question.
Final Answer: [your complete, helpful response to the user]
```

RULES:
1. NEVER output anything except these two formats
2. NEVER skip Action/Action Input after a Thought (unless it's Final Answer)
3. NEVER combine multiple actions in one response
4. After each tool result (Observation), respond with another Thought
5. Use Final Answer ONLY when you have enough information to answer completely

================================================================================

Begin!

Question: {input}
Thought: Let me analyze this question and determine which tool to use.
{agent_scratchpad}"""

        from langchain.prompts import PromptTemplate as LP
        prompt = LP(
            input_variables=["input", "agent_scratchpad", "tools", "tool_names"],
            template=prompt_template
        )

        agent = create_react_agent(self.llm, self.tools, prompt)
        
        # Custom parsing error handler that helps LLM recover
        def handle_parsing_error(error) -> str:
            """Handle parsing errors gracefully and guide LLM to correct format."""
            error_str = str(error)
            if "Could not parse LLM output" in error_str:
                # Extract the problematic output if available
                return (
                    "I notice you didn't follow the required format. "
                    "Please respond with EXACTLY this format:\n\n"
                    "Thought: [your reasoning about what to do next]\n"
                    "Action: [tool name - one of: student_context, business_school_database, assess_complexity, semantic_search, course_search]\n"
                    "Action Input: [the input for the tool]\n\n"
                    "OR if you have enough information to answer:\n\n"
                    "Thought: I now have the information needed to answer the question.\n"
                    "Final Answer: [your complete response to the user]"
                )
            return f"An error occurred: {error_str}. Please try again with the correct format."
        
        executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=False,  # Disabled verbose stdout callback to avoid callback errors
            max_iterations=10,  # Allow more iterations for complex queries like degree progress
            early_stopping_method="force",
            handle_parsing_errors=handle_parsing_error,
            return_intermediate_steps=True,  # Help debug issues
        )
        return executor

    async def answer_query(
        self,
        query: str,
        context: Optional[Any] = None,  # Can be ExtractedTranscriptData or TranscriptContext or StudentContext
        program_id: str = "msit",
        callbacks: Optional[List[AsyncCallbackHandler]] = None,
        session_id: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        topic_id: Optional[str] = None,  # Selected advising topic: 'general' or 'course'
    ) -> Dict[str, Any]:
        """
        Process a student query using agentic chat with RAG support.

        Args:
            query: Student's question
            context: Optional transcript context (StudentContext from session-based storage)
            program_id: Program identifier (msit, msba, msm)
            callbacks: Optional list of async callback handlers for streaming
            session_id: Session ID for context isolation

        Returns:
            Dict with response, reasoning, and tools used
        """
        try:
            logger.info(f"Processing query with adviser agent: {query[:50]}...")
            logger.info(f"Topic context: {topic_id or 'not specified'}")
            logger.info(f"Session ID: {session_id[:8] if session_id else 'None'}...")

            # Note: No Layer 3 hardcoded validation here anymore
            # Intent classification with Redis memory context already handles query meaningfulness
            # Short multi-turn responses (like "MSBA", "courses") are valid given conversation history
            logger.debug(f"Processing query (conversation history: {len(conversation_history) if conversation_history else 0} messages)")

            # Build topic-specific guidance
            topic_guidance = ""
            if topic_id == "general":
                topic_guidance = "\n[CONTEXT] User selected: General Advising - Focus on program overview, policies, degree requirements, specialization options."
                logger.info("Using General Advising topic guidance")
            elif topic_id == "course":
                topic_guidance = "\n[CONTEXT] User selected: Courses & Planning - Focus on course schedules, catalog details, prerequisites, course selection."
                logger.info("Using Courses & Planning topic guidance")
            else:
                logger.info("No specific topic selected, using general guidance")

            # Build conversation context from history if provided
            conversation_context = ""
            if conversation_history and len(conversation_history) > 0:
                context_parts = ["### CONVERSATION HISTORY (use this to understand context):"]
                # Include up to last 10 messages for context
                for msg in conversation_history[-10:]:
                    role = msg.get('role', 'unknown').upper()
                    content = msg.get('content', '')[:300]  # Limit message size
                    context_parts.append(f"{role}: {content}")
                conversation_context = "\n".join(context_parts) + "\n\n"
                logger.info(f"Including conversation history with {len(conversation_history)} messages for session {session_id}")

            # Check if this is a program/course question that MUST use DATABASE
            query_lower = query.lower()
            program_keywords = ['msit', 'msba', 'msm', 'course', 'requirement', 'specialization',
                               'graduation', 'prerequisite', 'program', 'core', 'degree', 'major']
            is_program_question = any(kw in query_lower for kw in program_keywords)

            if is_program_question:
                logger.info("Detected program/course question - USING DATABASE TOOL for authoritative data")
                # For program questions, directly use database tool to ensure accurate data
                try:
                    db_summary = business_school_db_tool(query)
                    if db_summary and db_summary.strip():
                        query_with_context = (
                            f"{query}\n\n[Business School Database Information]:\n{db_summary}"
                        )
                        logger.info(
                            "Business School database summary injected (%d chars)",
                            len(db_summary),
                        )
                    else:
                        query_with_context = query
                        logger.info("Database returned no results for program question")
                except Exception as db_err:
                    logger.error("Failed to fetch Business School database summary: %s", db_err)
                    query_with_context = query
            else:
                query_with_context = query

            # Student context is already stored in context_manager by session_id from transcript upload
            # The 'context' parameter here is the StudentContext object retrieved for this session
            has_transcript = False
            if context:
                from ..services.context_manager import StudentContext
                if isinstance(context, StudentContext) and context.has_transcript():
                    has_transcript = True
                    logger.info(f"Using StudentContext for session: student={context.student_name}, courses={len(context.courses)}")
                else:
                    logger.info("Context provided but not a valid StudentContext with transcript data")
            else:
                logger.info("No transcript context provided - user must upload PDF for personalized info")

            # Format input with context information, conversation history, and topic guidance
            input_text = self._format_agent_input(query_with_context, context, program_id, conversation_context, topic_guidance)

            # Execute agent
            logger.info("Executing Chat Agent with ReAct pattern...")
            result = await self.agent_executor.ainvoke({"input": input_text}, {"callbacks": callbacks})

            response = result.get("output", "")

            # Add guidance if query seems to be about personal progress without context
            if self._is_personal_progress_query(query) and not context:
                response += "\n\n**Note:** For personalized academic planning based on your transcript, please upload your PDF transcript to access your complete information."
                logger.info("Added transcript upload guidance to response")

            logger.info(f"Agent response generated: {len(response)} chars")

            return {
                "response": response,
                "reasoning": "Chat Agent used ReAct pattern with database-first tool use",
                "tools_used": ["business_school_database", "student_context", "assess_complexity"],
                "source": "database_first",
                "has_transcript": has_transcript
            }

        except Exception as e:
            logger.error(f"Error in adviser agent: {str(e)}", exc_info=True)
            raise ValueError(f"Agent processing failed: {str(e)}")

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
        conversation_context: str = "",
        topic_guidance: str = ""
    ) -> str:
        """Format the input for the agent, handling StudentContext from session-based storage"""
        from ..services.context_manager import StudentContext

        input_text = ""

        # Add conversation history if available
        if conversation_context:
            input_text += conversation_context

        # Add topic guidance if available
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
