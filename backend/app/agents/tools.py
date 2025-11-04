"""
Tool definitions for the academic adviser agent.
Provides tools for RAG retrieval, context lookup, and query analysis.
"""
from typing import List, Dict, Any, Optional
from langchain.tools import Tool
import logging

logger = logging.getLogger(__name__)


# Tool 1: RAG Retrieval for program information
def rag_retrieval_tool(query: str) -> str:
    """
    Search WPI Business School program knowledge base for:
    - Program overviews (MSIT, MSBA, MSM)
    - Core course requirements
    - Elective and specialization options
    - Program prerequisites and enrollment criteria
    - Course descriptions and learning outcomes

    Use this tool for ANY question about programs, courses, requirements, or specializations.
    Returns structured program information from the knowledge base.
    """
    try:
        from ..services.rag_service import get_rag_service

        logger.info(f"RAG tool invoked: {query[:50]}...")

        rag_service = get_rag_service()
        context = rag_service.get_context_for_query(
            query,
            program_id="msit",
            top_k=8,
            use_bm25=True
        )

        if context:
            logger.info(f"RAG retrieved {len(context)} chars of context")
            return f"Program Information Found:\n{context}"
        else:
            logger.warning("RAG returned no context")
            return "No relevant program information found in knowledge base."

    except Exception as e:
        logger.error(f"Error in RAG retrieval tool: {str(e)}")
        return f"Error retrieving information: {str(e)}"


# Tool 2: Student context lookup
def context_lookup_tool(info_type: str = "all") -> str:
    """
    Retrieve cached student transcript information for personalized advising.

    Use this tool when student asks about:
    - Their GPA, grades, or academic performance
    - Completed courses or course history
    - Current courses or academic progress
    - Program and enrollment information
    - Academic standing or recommendations

    Options: 'gpa', 'courses', 'program', 'progress', or 'all' for complete info.
    Returns: Empty if no transcript uploaded. Otherwise returns student academic data.
    """
    try:
        from ..services.context_manager import get_context_manager

        logger.info(f"Context lookup tool invoked for: {info_type}")

        context_manager = get_context_manager()
        student_context = context_manager.get_student_context()

        if not student_context:
            return "No student context available. Please upload a PDF transcript."

        result = []

        if info_type in ["all", "gpa"]:
            result.append(f"GPA: {student_context.gpa}/4.0")

        if info_type in ["all", "program"]:
            if student_context.program_info:
                result.append(f"Program: {student_context.program_info.program_name}")

        if info_type in ["all", "courses"]:
            if student_context.completed_courses:
                result.append(f"Completed Courses: {len(student_context.completed_courses)}")
            if student_context.current_courses:
                result.append(f"Current Courses: {len(student_context.current_courses)}")

        if info_type in ["all", "progress"]:
            progress = context_manager.get_academic_progress()
            if progress:
                result.append(f"Academic Standing: {progress.get('academic_standing', 'Unknown')}")
                result.append(f"Course Progression: {progress.get('course_progression', 'Unknown')}")

        return "\n".join(result) if result else "No student context available."

    except Exception as e:
        logger.error(f"Error in context lookup tool: {str(e)}")
        return f"Error retrieving context: {str(e)}"


# Tool 3: Query complexity assessment
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


# Initialize tools with proper formatting
RAG_RETRIEVAL_TOOL = Tool(
    name="rag_search",
    func=rag_retrieval_tool,
    description="Search program information from knowledge base. Use for course requirements, specializations, program structure, etc."
)

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


def get_all_tools() -> List[Tool]:
    """Get all available tools for the agent"""
    return [
        RAG_RETRIEVAL_TOOL,
        CONTEXT_LOOKUP_TOOL,
        COMPLEXITY_ASSESSMENT_TOOL
    ]
