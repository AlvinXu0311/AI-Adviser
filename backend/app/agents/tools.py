"""
Tool definitions for the academic adviser agent.
Provides tools for RAG retrieval, context lookup, and query analysis.
"""
from typing import List, Dict, Any, Optional
from langchain.tools import Tool
import logging

logger = logging.getLogger(__name__)


# Tool 1: Student context lookup
def context_lookup_tool(info_type: str = "all") -> str:
    """
    Retrieve cached student transcript information for personalized advising.

    Use this tool when student asks about:
    - Their GPA, grades, or academic performance
    - Completed courses or course history
    - Current courses or academic progress
    - Program and enrollment information
    - Academic standing or recommendations

    Options: 'gpa', 'courses', 'grades', 'program', 'progress', or 'all' for complete info.
    Returns: Empty if no transcript uploaded. Otherwise returns student academic data.
    """
    try:
        from ..services.context_manager import get_context_manager, get_current_session

        logger.info(f"Context lookup tool invoked for: {info_type}")

        # Get current session ID from context variable
        session_id = get_current_session()
        if not session_id:
            logger.warning("No session ID available in context lookup tool")
            return "No session context available. Please ensure you're in an active session."

        context_manager = get_context_manager()
        student_context = context_manager.get_student_context(session_id)

        if not student_context or not student_context.has_transcript():
            return "No student transcript uploaded for this session. Please upload a PDF transcript."

        result = []

        if info_type in ["all", "gpa"]:
            if student_context.gpa is not None:
                result.append(f"GPA: {student_context.gpa}/4.0")

        if info_type in ["all", "program"]:
            if student_context.degree_program:
                result.append(f"Program: {student_context.degree_program}")

        if info_type in ["all", "courses", "grades"]:
            if student_context.courses:
                # Build detailed course list with grades
                course_details = []
                for course in student_context.courses:
                    course_code = course.get('course_code', 'N/A')
                    course_name = course.get('course_name', 'Unknown')
                    credits = course.get('credits', 'N/A')
                    grade = course.get('grade')
                    grade_str = f", Grade: {grade}" if grade else ""
                    course_details.append(f"{course_code} - {course_name} ({credits} cr{grade_str})")
                completed_list = "\n  - ".join(course_details)
                result.append(f"Completed Courses ({len(student_context.courses)}):\n  - {completed_list}")

        if info_type in ["all", "progress"]:
            # Simplified progress info
            if student_context.courses:
                result.append(f"Total Courses Completed: {len(student_context.courses)}")
                if student_context.gpa:
                    if student_context.gpa >= 3.5:
                        result.append("Academic Standing: Good (Dean's List eligible)")
                    elif student_context.gpa >= 3.0:
                        result.append("Academic Standing: Good")
                    elif student_context.gpa >= 2.0:
                        result.append("Academic Standing: Satisfactory")
                    else:
                        result.append("Academic Standing: Academic Warning")

        return "\n".join(result) if result else "No student transcript data available for this session."

    except Exception as e:
        logger.error(f"Error in context lookup tool: {str(e)}")
        return f"Error retrieving context: {str(e)}"


# Tool 2: Query complexity assessment
def complexity_assessment_tool(query: str) -> str:
    """
    Assess query complexity to determine optimal reasoning approach:
    - SIMPLE: Factual lookup (course code, program name, basic requirements)
    - MEDIUM: Moderate reasoning (course planning, comparing options, prerequisites)
    - COMPLEX: Deep analysis (personalized path planning, multi-factor decisions)

    Use this tool to understand the question before deciding on tool strategy.
    Guides the depth of tools needed and answer complexity.
    """
    try:
        complexity = _assess_complexity(query)
        details = f"Query Complexity Assessment: {complexity.upper()}\n\nReasoning Hints:\n"

        if complexity == "simple":
            details += "- Straightforward factual lookup\n"
            details += "- Direct answer without reasoning\n"
            details += "- Minimal context needed\n"
        elif complexity == "medium":
            details += "- Requires some analysis\n"
            details += "- May need to relate multiple pieces of information\n"
            details += "- Consider student context if available\n"
        else:  # complex
            details += "- Multi-part question requiring detailed reasoning\n"
            details += "- Compare options or explain trade-offs\n"
            details += "- Integrate program requirements with student context\n"

        return details

    except Exception as e:
        logger.error(f"Error in complexity assessment tool: {str(e)}")
        return f"Error assessing complexity: {str(e)}"


def _assess_complexity(query: str) -> str:
    """Internal helper to assess query complexity"""
    query_lower = query.lower()

    complex_indicators = [
        "explain", "why", "how does", "compare",
        "analyze", "evaluate", "what if", "recommend",
        "pros and cons", "best way"
    ]

    medium_indicators = [
        "what are", "tell me", "describe", "requirements",
        "which", "list", "show me"
    ]

    simple_indicators = [
        "what is my", "my gpa", "my grade",
        "when is", "true or false"
    ]

    if any(ind in query_lower for ind in simple_indicators):
        return "simple"

    if any(ind in query_lower for ind in complex_indicators):
        return "complex"

    if any(ind in query_lower for ind in medium_indicators):
        return "medium"

    return "medium" if len(query.split()) > 15 else "simple"


def business_school_db_tool(query: str) -> str:
    """Query the authoritative Business School SQLite database for program data."""
    try:
        from ..services.program_db_service import get_program_db_service

        logger.info("Business School DB tool invoked")
        service = get_program_db_service()
        return service.summarize_programs(query)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error in Business School DB tool: %s", exc)
        return f"Database lookup failed: {exc}"


def semantic_search_tool(query: str) -> str:
    """
    Semantic search across all academic entities using Google Embeddings + ChromaDB.
    
    Searches:
    - Courses: by topic, description, instructor name
    - Programs: by name, description, requirements  
    - Specialties: by focus area, description
    
    Uses hybrid approach: vector similarity + keyword matching for best results.
    Returns detailed info including instructors, credits, descriptions.
    """
    try:
        from ..services.vector_search_service import get_vector_search_service
        
        logger.info(f"Semantic search tool invoked for: {query}")
        service = get_vector_search_service()
        return service.search(query, top_k=5)
    except Exception as exc:
        logger.error("Error in semantic search tool: %s", exc)
        return f"Semantic search failed: {exc}"


def course_search_tool(query: str) -> str:
    """
    Search specifically for courses using semantic + keyword matching.
    
    Best for finding:
    - Courses by topic (e.g., 'data mining', 'machine learning')
    - Instructor information (e.g., 'Who teaches marketing?')
    - Course details by code (e.g., 'MIS 500')
    
    Returns: course code, title, credits, instructors, description.
    """
    try:
        from ..services.vector_search_service import get_vector_search_service, EntityType
        
        logger.info(f"Course search tool invoked for: {query}")
        service = get_vector_search_service()
        return service.search(query, entity_type=EntityType.COURSE, top_k=5)
    except Exception as exc:
        logger.error("Error in course search tool: %s", exc)
        return f"Course search failed: {exc}"


# Initialize tools with proper formatting
CONTEXT_LOOKUP_TOOL = Tool(
    name="student_context",
    func=context_lookup_tool,
    description="Look up student transcript information. Input: 'gpa', 'courses', 'program', 'progress', or 'all'"
)

COMPLEXITY_ASSESSMENT_TOOL = Tool(
    name="assess_complexity",
    func=complexity_assessment_tool,
    description="Assess query complexity to determine reasoning approach needed."
)

BUSINESS_SCHOOL_DB_TOOL = Tool(
    name="business_school_database",
    func=business_school_db_tool,
    description=(
        "Look up official Business School program structure from SQLite database. "
        "Best for: listing all programs, specialties, degree requirements. "
        "Input: program code (e.g., 'MSIT', 'MSBA') or 'all' for overview."
    )
)

SEMANTIC_SEARCH_TOOL = Tool(
    name="semantic_search",
    func=semantic_search_tool,
    description=(
        "Semantic search across courses, programs, and specialties using AI embeddings. "
        "Best for: finding info by topic/concept when you don't know exact names. "
        "Input: natural language query (e.g., 'machine learning courses', 'data analytics program'). "
        "Returns: matched courses, programs, specialties with details."
    )
)

COURSE_SEARCH_TOOL = Tool(
    name="course_search",
    func=course_search_tool,
    description=(
        "Search for courses using semantic + keyword matching. "
        "Best for: finding courses by topic, getting instructor info. "
        "Input: topic (e.g., 'data mining'), code (e.g., 'MIS 500'), or instructor query. "
        "Returns: course code, title, credits, instructors, description."
    )
)


def get_all_tools() -> List[Tool]:
    """Get all available tools for the agent"""
    return [
        CONTEXT_LOOKUP_TOOL,
        COMPLEXITY_ASSESSMENT_TOOL,
        BUSINESS_SCHOOL_DB_TOOL,
        SEMANTIC_SEARCH_TOOL,
        COURSE_SEARCH_TOOL,
    ]
