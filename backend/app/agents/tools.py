"""
Tool definitions for the academic adviser agent.
Provides tools for database-first search, RAG retrieval, and student context lookup.
"""
from typing import List
from langchain_core.tools import StructuredTool
import logging

from ..services.search_service import (
    business_school_db_tool,
    pdf_context_tool,
    program_search_tool,
    semantic_search_tool,
    smart_course_search_tool,
)

logger = logging.getLogger(__name__)


# Student context lookup
def context_lookup_tool(info_type: str = "all") -> str:
    """
    Retrieve cached student transcript information for personalized advising.

    Use this tool when student asks about:
    - Their GPA, grades, or academic performance
    - Completed courses or course history
    - Current courses they are currently taking
    - Program and enrollment information
    - Academic standing or recommendations

    Options: 'gpa', 'courses', 'current', 'grades', 'program', 'progress', or 'all' for complete info.
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

        if info_type in ["all", "current"]:
            # Show currently enrolled courses
            current_courses = getattr(student_context, 'current_courses', [])
            if current_courses:
                current_details = []
                for course in current_courses:
                    course_code = course.get('course_code', 'N/A')
                    course_name = course.get('course_name', 'Unknown')
                    credits = course.get('credits', 'N/A')
                    semester = course.get('semester', '')
                    semester_str = f" - {semester}" if semester else ""
                    current_details.append(f"{course_code} - {course_name} ({credits} cr){semester_str}")
                current_list = "\n  - ".join(current_details)
                result.append(f"Currently Enrolled ({len(current_courses)}):\n  - {current_list}")
            else:
                result.append("Currently Enrolled: No current courses found in transcript")

        if info_type in ["all", "progress"]:
            # Simplified progress info
            completed_count = len(student_context.courses) if student_context.courses else 0
            current_count = len(getattr(student_context, 'current_courses', [])) if hasattr(student_context, 'current_courses') else 0
            result.append(f"Total Courses Completed: {completed_count}")
            if current_count > 0:
                result.append(f"Currently Taking: {current_count} courses")
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


def degree_progress_tool(program_name: str) -> str:
    """
    Compare student's completed courses against program requirements.
    
    This tool uses the student's transcript data and compares it against
    the official program requirements in the Business School database.
    
    Best for answering:
    - "How close am I to graduating?"
    - "What courses do I still need for MSIT?"
    - "What are my remaining requirements?"
    - "Have I completed the MBA prerequisites?"
    
    Input: Program name to check against (e.g., 'MBA', 'MSIT', 'MSBA')
    Returns: Detailed progress report showing completed and missing requirements.
    """
    try:
        from ..services.program_db_service import get_program_db_service
        from ..services.context_manager import get_context_manager, get_current_session
        
        logger.info(f"Degree progress tool invoked for program: {program_name}")
        
        # Get current session and student context
        session_id = get_current_session()
        if not session_id:
            return "No session context available. Please ensure you're in an active session."
        
        context_manager = get_context_manager()
        student_context = context_manager.get_student_context(session_id)
        
        if not student_context or not student_context.has_transcript():
            return "No student transcript uploaded. Please upload a PDF transcript first to check your degree progress."
        
        # Extract completed course codes
        completed_courses = []
        if student_context.courses:
            for course in student_context.courses:
                code = course.get('course_code', '')
                if code:
                    completed_courses.append(code)
        
        # Extract current course codes
        current_courses = []
        if hasattr(student_context, 'current_courses') and student_context.current_courses:
            for course in student_context.current_courses:
                code = course.get('course_code', '')
                if code:
                    current_courses.append(code)
        
        if not completed_courses and not current_courses:
            return "No course data found in transcript. Please ensure transcript contains course information."
        
        # Get the database service and compare
        service = get_program_db_service()
        analysis = service.compare_student_progress(
            program_name, 
            completed_courses,
            current_courses
        )
        
        return service.format_progress_report(analysis)
        
    except Exception as exc:
        logger.error("Error in degree progress tool: %s", exc)
        return f"Degree progress check failed: {exc}"



# NOTE: course_search_tool has been removed - use smart_course_search_tool instead
# which uses the unified_search layer with DB-first strategy


# Initialize tools with proper formatting
CONTEXT_LOOKUP_TOOL = StructuredTool.from_function(
    name="student_context",
    func=context_lookup_tool,
    description="Look up student transcript information. Input: 'gpa', 'courses', 'program', 'progress', or 'all'"
)

BUSINESS_SCHOOL_DB_TOOL = StructuredTool.from_function(
    name="business_school_database",
    func=business_school_db_tool,
    description=(
        "Look up official Business School program structure from SQLite database. "
        "Best for: listing all programs, specialties, degree requirements. "
        "Input: program code (e.g., 'MSIT', 'MSBA') or 'all' for overview."
    )
)

SMART_COURSE_SEARCH_TOOL = StructuredTool.from_function(
    name="smart_course_search",
    func=smart_course_search_tool,
    description=(
        "PRIMARY tool for course questions. Searches DB first (has instructor, credits, schedule), "
        "then PDF catalogs for descriptions. Best for: 'Who teaches X?', 'What is course X about?', "
        "'Course prerequisites', 'Find courses on topic Y'. Input: course name, code, or topic."
    )
)

DEGREE_PROGRESS_TOOL = StructuredTool.from_function(
    name="degree_progress",
    func=degree_progress_tool,
    description=(
        "Compare student's transcript against program requirements. "
        "Shows: which specialties are complete, remaining courses needed, graduation status. "
        "REQUIRES uploaded transcript. Input: program name (e.g., 'MBA', 'MSIT', 'MSBA'). "
        "Best for: 'How close am I to graduating?', 'What do I still need for MBA?'"
    )
)

SEMANTIC_SEARCH_TOOL = StructuredTool.from_function(
    name="semantic_search",
    func=semantic_search_tool,
    description=(
        "General semantic search across academic PDF documents. "
        "FALLBACK tool when specific tools don't find results. "
        "Uses unified search with retry logic. "
        "Input: natural language query."
    )
)

PROGRAM_SEARCH_TOOL = StructuredTool.from_function(
    name="program_search",
    func=program_search_tool,
    description=(
        "Search for program/degree information (MBA, MSIT, MSBA, etc.). "
        "Uses DB-first strategy with RAG fallback. "
        "Best for: program requirements, specialties, degree structure. "
        "Input: program name or keyword."
    )
)

PDF_CONTEXT_TOOL = StructuredTool.from_function(
    name="pdf_context",
    func=pdf_context_tool,
    description=(
        "Get comprehensive context from academic PDFs for complex questions. "
        "Returns longer, concatenated sections from multiple sources. "
        "Best for: detailed program requirements, comparing options, in-depth analysis. "
        "Input: detailed question needing extensive context."
    )
)


def get_all_tools() -> List[StructuredTool]:
    """Get all available tools for the agent.
    
    Tool hierarchy:
    1. SMART_COURSE_SEARCH_TOOL - Course questions (who teaches, prerequisites, etc.)
    2. PROGRAM_SEARCH_TOOL - Program/degree requirements
    3. DEGREE_PROGRESS_TOOL - Student progress against requirements (needs transcript)
    4. BUSINESS_SCHOOL_DB_TOOL - Direct DB queries for program structure
    5. SEMANTIC_SEARCH_TOOL - General fallback search
    6. CONTEXT_LOOKUP_TOOL - Student transcript info
    7. PDF_CONTEXT_TOOL - Detailed context for complex questions
    """
    return [
        SMART_COURSE_SEARCH_TOOL,  # Primary for course questions
        PROGRAM_SEARCH_TOOL,       # Primary for program questions
        DEGREE_PROGRESS_TOOL,      # For student progress
        BUSINESS_SCHOOL_DB_TOOL,   # Direct DB access
        SEMANTIC_SEARCH_TOOL,      # Fallback search
        CONTEXT_LOOKUP_TOOL,       # Student transcript
        PDF_CONTEXT_TOOL,          # Detailed context
    ]
