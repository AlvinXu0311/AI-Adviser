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
        
        # Dynamically fetch available programs from database
        self.available_programs = get_available_programs()
        self.program_list_str = get_program_list_for_prompt()
        logger.info(f"Loaded available programs: {self.available_programs}")

        # Improved system prompt for agentic reasoning with DB-First architecture
        self.system_prompt = f"""You are an expert Academic Adviser for WPI Business School.
    Your expertise: Programs ({', '.join(self.available_programs)}), course requirements, specializations, student academic planning, and academic catalogs.

CORE RESPONSIBILITIES:
1. Answer student questions about degree programs, requirements, and courses
2. Help plan academic paths based on student background and goals
3. Provide guidance on specializations and elective options
4. Address questions about student transcripts and academic progress (if uploaded)

ARCHITECTURE: UNIFIED SEARCH (DB-first → RAG fallback with retry logic)

All search tools use a common strategy:
1. Try DB search (SQL) - most accurate, structured data
2. Try RAG search (semantic) - PDF catalogs  
3. Retry 2-3 times with query variations before giving up

MANDATORY TOOL USAGE (ReAct Pattern):
You MUST use tools for every question. Here's the priority:

1. COURSE QUESTIONS - Use smart_course_search (PRIMARY):
   - "Who teaches X?" → smart_course_search
   - "What is MIS 520 about?" → smart_course_search
   - "Course prerequisites/credits" → smart_course_search
   - "Find courses on topic Y" → smart_course_search

2. PROGRAM/DEGREE QUESTIONS - Use program_search:
   - "What is MSIT?" → program_search
   - "MBA requirements" → program_search
   - "Program specializations" → program_search

3. DEGREE PROGRESS - Use degree_progress:
   - "What courses do I still need?" → degree_progress
   - "Am I close to graduating?" → degree_progress
   - REQUIRES uploaded transcript

4. PERSONAL INFO - Use student_context:
   - "What's my GPA?" → student_context
   - "My courses" → student_context

5. GENERAL/FALLBACK - Use semantic_search:
   - When specific tools return nothing
   - General academic questions

CRITICAL RULES:
- For "Who teaches X?" questions: ALWAYS use smart_course_search first
- ONLY use tool-provided data - never invent course codes, credits, or requirements
- Always cite your source: "According to the database..." or "Based on the catalog..."
- If all tools return nothing, say: "I don't have that information available"
- For personal questions without transcript: suggest uploading a PDF"""

        self.agent_executor = self._create_agent()

    def _create_agent(self) -> AgentExecutor:
        """Create the ReAct agent with optimized prompt for agentic reasoning"""
        
        # Build prompt template with dynamic program list
        # Use double braces for LangChain placeholders, single for our replacement
        prompt_template_raw = """You are an expert Academic Adviser for WPI Business School.

SYSTEM CONTEXT:
You help students with program information, course planning, and academic guidance.
You have access to:
- Business School SQLite database (AUTHORITATIVE source)
- PDF Academic Catalogs via semantic search (FALLBACK)
- Student transcript cache (if uploaded)

ARCHITECTURE: UNIFIED SEARCH (DB-first → RAG fallback with retry logic)

AVAILABLE TOOLS:
1. smart_course_search - Search for specific course info (instructor, credits, description)
2. program_search - Search for program requirements, specializations
3. degree_progress - Compare student progress against program (requires transcript)
4. student_context - Get student's personal info (GPA, courses)
5. semantic_search - General search across PDF catalogs
6. business_school_database - Direct database queries
7. assess_complexity - Analyze query complexity

================================================================================
MULTI-STEP REASONING (IMPORTANT!):
================================================================================

For COMPLEX questions, you should use MULTIPLE tools in sequence:

EXAMPLE 1: "What analytics courses should I take for MBA?"
- Step 1: Use program_search("MBA analytics specialization") → get required courses
- Step 2: Use smart_course_search("MIS 502") → get course details
- Step 3: Use smart_course_search("OIE 552") → get more course details
- Final Answer: Combine all information

EXAMPLE 2: "I want to focus on AI/ML, what courses and programs fit?"
- Step 1: Use smart_course_search("machine learning AI courses") → find ML courses
- Step 2: Use program_search("data science program") → check MSBA
- Step 3: Use semantic_search("artificial intelligence curriculum") → broader search
- Final Answer: Synthesize recommendations

EXAMPLE 3: "Compare MSIT and MSBA for someone interested in data"
- Step 1: Use program_search("MSIT requirements") → get MSIT info
- Step 2: Use program_search("MSBA requirements") → get MSBA info  
- Step 3: Use smart_course_search("data analytics courses") → relevant courses
- Final Answer: Compare and contrast

EXAMPLE 4: "Who teaches database courses and what are the prerequisites?"
- Step 1: Use smart_course_search("database courses") → find courses
- Step 2: Use smart_course_search("MIS 571 prerequisites") → get prereqs
- Final Answer: Provide instructor + prerequisites

================================================================================
CONVERSATIONAL BEHAVIOR (IMPORTANT!):
================================================================================

ASK CLARIFYING QUESTIONS when:
- User hasn't specified which program they are in or interested in
- User asks for course recommendations without context
- User's goals or interests are unclear
- User asks "what should I take?" without background info

EXAMPLES OF WHEN TO ASK FIRST:
- "What courses should I take?" → ASK: "Which program are you enrolled in (MSIT, MSBA, MBA, etc.)? And what are your career goals or interests?"
- "Recommend me some electives" → ASK: "What program are you in? Do you have any specific areas of interest (AI/ML, analytics, management, etc.)?"
- "Am I on track?" → ASK: "Have you uploaded your transcript? Which degree program are you pursuing?"

DO NOT ASSUME:
- Never assume the user is in a specific program unless they told you
- Never assume career goals unless explicitly stated
- If user uploaded a transcript, check student_context first to see their program

GOOD CONVERSATIONAL FLOW:
1. User: "What courses are good for ML?"
2. Agent: First ASK → "Great question! To give you the best recommendations, could you tell me:
   - Which program are you enrolled in (MSIT, MSBA, MBA)?
   - Are you looking for introductory or advanced ML courses?"
3. User: "I'm in MSIT"
4. Agent: NOW search → program_search("MSIT AI specialization") + smart_course_search("machine learning")

================================================================================
DEGREE PROGRESS VERIFICATION (CRITICAL!):
================================================================================

When user asks about DEGREE PROGRESS, GRADUATION STATUS, or REMAINING COURSES:
- "Check my progress", "What do I still need?", "Am I close to graduating?"
- "How many credits left?", "What courses remain?"

YOU MUST VERIFY THESE CONDITIONS BEFORE USING degree_progress TOOL:

1. TRANSCRIPT CHECK: Has user uploaded a transcript?
   - If NO → "To check your degree progress, please upload your transcript first using the paperclip icon."

2. PROGRAM CONFIRMATION: Which program is the student in?
   - SUPPORTED PROGRAMS: See "AVAILABLE PROGRAMS" section below (fetched from database)
   - If program is UNCLEAR → "Which program are you enrolled in?" (then list available programs)
   - If program is NOT in our database → Tell user the program is not supported and list available ones

3. DOUBLE-CHECK before running degree_progress:
   - Confirm: "Just to confirm - you're in the [PROGRAM] program, correct? I'll check your remaining requirements."

EXAMPLE FLOW FOR DEGREE PROGRESS:
1. User: "Check my degree progress"
2. Agent: First use student_context to check if transcript exists and get program
3. If no transcript → Ask to upload
4. If transcript exists but program unclear → "I see you've uploaded a transcript. Which program are you pursuing?" (list available programs)
5. User: "MSIT"  
6. Agent: "Great! Checking your MSIT progress now..." → degree_progress("MSIT")

================================================================================
AVAILABLE PROGRAMS AT WPI BUSINESS SCHOOL (FETCHED FROM DATABASE):
================================================================================

ONLY THESE PROGRAMS ARE IN OUR DATABASE (degree_progress ONLY works for these):
<<AVAILABLE_PROGRAMS>>

IMPORTANT: Do NOT accept or process degree progress for programs outside this list.
If user mentions a program not listed above, tell them: 
"I don't have [program name] in my database. Let me check what programs are available..." 
Then use the programs listed above.

================================================================================
WHEN TO USE MULTIPLE TOOLS:
================================================================================

USE 2-3 TOOLS when the question involves:
- Comparing programs or options → search each separately
- Getting course details after finding program requirements
- Verifying information from multiple sources
- Building a study plan or path
- "Best" or "recommended" questions → need multiple data points

USE 1 TOOL when the question is:
- Simple factual lookup ("Who teaches X?")
- Single course or program inquiry
- Personal info request (GPA, grades)

================================================================================
TOOL SELECTION GUIDE:
================================================================================

1. COURSE QUESTIONS ("Who teaches X?", "What is course X?", credits, prerequisites):
   → Use smart_course_search (PRIMARY)
   → Example: "Who teaches MIS 520?" → smart_course_search

2. PROGRAM/DEGREE QUESTIONS (requirements, specializations, structure):
   → Use program_search
   → Example: "What is MSIT?", "MBA requirements" → program_search
   
3. DEGREE PROGRESS ("What do I still need?", "Am I close to graduating?"):
   → Use degree_progress (requires transcript upload)
   → Input: program name like "MBA", "MSIT", "MSBA"

4. PERSONAL INFO (GPA, completed courses, current courses):
   → Use student_context
   
5. GENERAL/FALLBACK (when specific tools return nothing):
   → Use semantic_search

================================================================================
RESPONSE FORMAT (STRICTLY REQUIRED):
================================================================================

You MUST respond in ONE of these two formats ONLY:

FORMAT A - When you need to use a tool:
```
Thought: [your reasoning - be specific about what you're looking for and why]
Action: [exactly one tool name from: {tool_names}]
Action Input: [the input string for the tool]
```

FORMAT B - When you have gathered ENOUGH information (after multiple tool uses if needed):
```
Thought: I have gathered sufficient information from [list tools used]. Now I can provide a comprehensive answer.
Final Answer: [your complete, well-organized response with all gathered information]
```

RULES:
1. For complex questions, use 2-3 tools before Final Answer
2. After each tool result (Observation), evaluate: "Do I have enough info or need more?"
3. NEVER answer without citing your sources
4. NEVER invent information - only use what tools provide

You have access to the following tools:

{tools}

Tool names: {tool_names}

================================================================================

Begin!

Question: {input}
Thought: Let me analyze this question. I'll determine what information I need and which tool(s) to use.
{agent_scratchpad}"""

        # Replace the dynamic placeholder with actual program list from database
        prompt_template = prompt_template_raw.replace(
            "<<AVAILABLE_PROGRAMS>>", 
            self.program_list_str
        )

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
                    "Action: [tool name - one of: smart_course_search, program_search, degree_progress, business_school_database, semantic_search, student_context, pdf_context]\n"
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
                # Include up to last 20 messages for better context retention
                for msg in conversation_history[-20:]:
                    role = msg.get('role', 'unknown').upper()
                    content = msg.get('content', '')[:500]  # Allow longer message context
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
