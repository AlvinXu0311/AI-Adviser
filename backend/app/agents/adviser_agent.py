"""
Academic Adviser Agent using LangChain with ReAct pattern.
Autonomous agent that handles student queries through intelligent reasoning and tool use.
"""
from typing import Optional, Any, Dict
from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
import logging
import os

from ..schemas.chat import TranscriptContext
from .tools import get_all_tools
from ..services.context_manager import get_context_manager

logger = logging.getLogger(__name__)


class AdviserAgent:
    """
    Chat Agent using LangChain's ReAct pattern for conversational advising.
    Uses RAG Agent for knowledge retrieval and maintains conversation flow.
    Handles academic advising with autonomous decision-making and tool use.

    Architecture:
    - Chat Agent: Handles conversation logic and user interaction
    - RAG Agent: Retrieves program information from knowledge base
    - Tools: rag_search (via RAG Agent), student_context, complexity_assessment
    """

    def __init__(self):
        """Initialize the adviser agent with tools and language model"""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")

        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.7,
            max_output_tokens=2048,
            google_api_key=api_key
        )

        # Initialize RAG agent for knowledge retrieval
        from .rag_agent import get_rag_agent
        self.rag_agent = get_rag_agent()

        self.tools = get_all_tools()

        # Improved system prompt for agentic reasoning
        self.system_prompt = """You are an expert Academic Adviser for WPI Business School.
Your expertise: Programs (MSIT, MSBA, MSM), course requirements, specializations, and student academic planning.

CORE RESPONSIBILITIES:
1. Answer student questions about degree programs, requirements, and courses
2. Help plan academic paths based on student background and goals
3. Provide guidance on specializations and elective options
4. Address questions about student transcripts and academic progress (if uploaded)

TOOL USAGE STRATEGY (ReAct Pattern):
You have three tools available - use them strategically:
1. rag_search: Use for program/course knowledge questions
2. student_context: Use ONLY for personal academic progress questions
3. assess_complexity: Use to understand question depth before responding

CRITICAL RULES:
- ONLY answer based on information from tools or knowledge base
- NEVER invent course codes, credits, or program details
- If tools return no information, respond: "I don't have that information in the knowledge base"
- Be concise (2-3 sentences max unless detailed explanation needed)
- Answer the specific question - no unsolicited advice
- For personal questions without transcript: suggest uploading a PDF"""

        self.agent_executor = self._create_agent()

    def _create_agent(self) -> AgentExecutor:
        """Create the ReAct agent with optimized prompt for agentic reasoning"""
        prompt_template = """You are an expert Academic Adviser for WPI Business School.

SYSTEM CONTEXT:
You help students with program information, course planning, and academic guidance.
You have access to:
- Knowledge base of 3 programs (MSIT, MSBA, MSM) with courses and requirements
- Student transcript cache (if they uploaded their PDF)
- Query complexity assessment tool

AGENTIC REASONING (ReAct Pattern):
For EVERY question, follow this thinking process:

1. ANALYZE: What type of question is this?
   - Program/course question → Use rag_search
   - Personal progress question → Use student_context first
   - Complex question → Use assess_complexity to understand depth

2. ACT: Use one or two tools strategically
   - Retrieve the MINIMUM information needed
   - Don't use same tool twice
   - Use results to form accurate answer

3. RESPOND: Provide final answer
   - Reference specific courses/programs when applicable
   - Cite information from tools, not general knowledge
   - Be direct and concise

CRITICAL CONSTRAINTS:
- ONLY use tool-provided information (no general knowledge about WPI)
- NEVER make up: course codes, credit values, requirements, or program details
- If information unavailable, explicitly say so
- Maximum 2-3 tools per question

You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
Thought: I now have the information I need to answer
Final Answer: the final answer to the original input question

IMPORTANT: After getting an Observation from a tool, provide your Final Answer immediately. Do NOT use the same tool twice.

Begin!

Question: {input}
Thought:{agent_scratchpad}"""

        from langchain.prompts import PromptTemplate as LP
        prompt = LP(
            input_variables=["input", "agent_scratchpad", "tools", "tool_names"],
            template=prompt_template
        )

        agent = create_react_agent(self.llm, self.tools, prompt)
        executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=5,  # Reduced from 10 to prevent looping
            early_stopping_method="force",
            handle_parsing_errors=True  # Allow agent to recover from parsing errors
        )
        return executor

    async def answer_query(
        self,
        query: str,
        context: Optional[Any] = None,  # Can be ExtractedTranscriptData or TranscriptContext
        program_id: str = "msit"
    ) -> Dict[str, Any]:
        """
        Process a student query using agentic chat with RAG support.

        Args:
            query: Student's question
            context: Optional transcript context (ExtractedTranscriptData from PDF or TranscriptContext from API)
            program_id: Program identifier (msit, msba, msm)

        Returns:
            Dict with response, reasoning, and tools used
        """
        try:
            logger.info(f"Processing query with adviser agent: {query[:50]}...")

            # Store context for tool access
            if context:
                context_manager = get_context_manager()
                from ..schemas.transcript import ExtractedTranscriptData, ProgramInfo

                # Check if we already have ExtractedTranscriptData (from PDF) or need to convert
                if isinstance(context, ExtractedTranscriptData):
                    # Already full transcript data from PDF - use it directly
                    logger.info(f"Using full ExtractedTranscriptData for student: {context.student_name}")
                    logger.info(f"  - Student ID: {context.student_id}")
                    logger.info(f"  - GPA: {context.gpa}")
                    logger.info(f"  - Completed courses: {len(context.completed_courses) if context.completed_courses else 0}")
                    logger.info(f"  - Current courses: {len(context.current_courses) if context.current_courses else 0}")
                    context_manager.set_student_context(context)
                else:
                    # Convert TranscriptContext (from API) to ExtractedTranscriptData
                    transcript_data = ExtractedTranscriptData(
                        student_name=context.student_name,
                        student_id=context.student_name or "N/A",  # Limited info from API
                        gpa=context.gpa,
                        program_info=ProgramInfo(program_name=context.program) if context.program else None,
                        completed_courses=[],
                        current_courses=[]
                    )
                    logger.info(f"Converted TranscriptContext for student: {context.student_name}")
                    context_manager.set_student_context(transcript_data)
            else:
                logger.info("No transcript context provided - user must upload PDF for personalized info")

            # Format input with context information
            input_text = self._format_agent_input(query, context, program_id)

            # Execute agent
            logger.info("Executing Chat Agent with ReAct pattern...")
            result = await self.agent_executor.ainvoke({"input": input_text})

            response = result.get("output", "")

            # Add guidance if query seems to be about personal progress without context
            if self._is_personal_progress_query(query) and not context:
                response += "\n\n**Note:** For personalized academic planning based on your transcript, please upload your PDF transcript to access your complete information."
                logger.info("Added transcript upload guidance to response")

            logger.info(f"Agent response generated: {len(response)} chars")

            return {
                "response": response,
                "reasoning": "Chat Agent used ReAct pattern with tool use for knowledge retrieval",
                "tools_used": ["rag_search", "student_context", "assess_complexity"],
                "source": "agentic_rag",
                "has_transcript": context is not None
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
        program_id: str = "msit"
    ) -> str:
        """Format the input for the agent, handling both TranscriptContext and ExtractedTranscriptData"""
        from ..schemas.transcript import ExtractedTranscriptData

        input_text = f"Student Question: {query}\n"

        if context:
            input_text += f"\nStudent Context:\n"

            # Handle ExtractedTranscriptData (from PDF extraction)
            if isinstance(context, ExtractedTranscriptData):
                if context.student_name:
                    input_text += f"- Name: {context.student_name}\n"
                if context.student_id:
                    input_text += f"- Student ID: {context.student_id}\n"
                if context.gpa is not None:
                    input_text += f"- GPA: {context.gpa}/4.0\n"
                if context.program_info and context.program_info.program_name:
                    input_text += f"- Program: {context.program_info.program_name}\n"

                # Count completed and current courses
                completed_count = len(context.completed_courses) if context.completed_courses else 0
                current_count = len(context.current_courses) if context.current_courses else 0

                if completed_count > 0:
                    input_text += f"- Completed Courses: {completed_count}\n"
                if current_count > 0:
                    input_text += f"- Current Courses: {current_count}\n"

            # Handle TranscriptContext (legacy format from API)
            else:
                if context.student_name:
                    input_text += f"- Name: {context.student_name}\n"
                if context.gpa is not None:
                    input_text += f"- GPA: {context.gpa}/4.0\n"
                if hasattr(context, 'program') and context.program:
                    input_text += f"- Program: {context.program}\n"
                if hasattr(context, 'course_count') and context.course_count is not None:
                    input_text += f"- Courses Completed: {context.course_count}\n"

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
