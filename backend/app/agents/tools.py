"""
Tool definitions for the academic adviser agent.
Provides tools for RAG retrieval, context lookup, and query analysis.
"""
from typing import List, Dict, Any, Optional, Callable
from langchain.tools import Tool
import logging
import re

logger = logging.getLogger(__name__)


# =============================================================================
# UNIFIED SEARCH LAYER
# =============================================================================
# All search tools share this common logic:
# 1. DB Search (SQL) → Most accurate, structured data
# 2. Semantic Search (RAG) → Semantic matching from PDFs  
# 3. Keyword Search → Exact pattern matching
# Loop 2-3 times with different query variations before giving up
# =============================================================================

def unified_search(
    query: str,
    search_type: str = "general",
    db_search_func: Optional[Callable] = None,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Unified search strategy: DB first → Semantic search → Keyword search.
    
    Args:
        query: The search query
        search_type: Type of search ('course', 'program', 'professor', 'general')
        db_search_func: Optional custom DB search function
        max_retries: Maximum retry attempts with query variations
    
    Returns:
        Dict with 'db_results', 'rag_results', 'source' keys
    """
    from ..services.program_db_service import get_program_db_service
    from ..services.pdf_vector_service import get_pdf_vector_service
    
    results = {
        'db_results': None,
        'rag_results': None,
        'source': None,
        'found': False
    }
    
    # Clean query for searching
    clean_query = _clean_query(query)
    
    # Extract course code from ORIGINAL query for validation (not from variations)
    original_code_match = re.search(r'([A-Z]{2,4})\s*(\d{3,4})', query.upper())
    expected_dept = original_code_match.group(1) if original_code_match else None
    expected_number = original_code_match.group(2) if original_code_match else None
    
    logger.info(f"Unified search: query='{query}', expected_dept={expected_dept}, expected_number={expected_number}")
    
    # Generate query variations for retry logic
    query_variations = _generate_query_variations(clean_query, search_type)
    
    # Step 1: Try DB search first (most accurate)
    try:
        db_service = get_program_db_service()
        
        for i, q_var in enumerate(query_variations[:max_retries]):
            logger.info(f"DB search attempt {i+1}/{max_retries}: '{q_var}'")
            
            if db_search_func:
                db_result = db_search_func(q_var)
            elif search_type == "course":
                db_result = db_service.summarize_courses(q_var)
            elif search_type == "program":
                db_result = db_service.summarize_programs(q_var)
            elif search_type == "professor":
                db_result = db_service.summarize_courses(q_var)  # Courses have instructor info
            else:
                db_result = db_service.summarize_courses(q_var)
            
            if db_result and _has_valid_results(db_result):
                # For course searches, ALWAYS validate that the result matches the expected course code
                if search_type == "course" and expected_dept and expected_number:
                    # Check if DB result contains the expected department code (e.g., "MA" for MA 571)
                    # Look for pattern like "MA 571" or "MA-571" in result
                    expected_pattern = rf'\b{expected_dept}\s*[-/]?\s*{expected_number}\b'
                    if not re.search(expected_pattern, db_result.upper()):
                        logger.info(f"DB result doesn't match expected course {expected_dept} {expected_number}, skipping...")
                        continue  # Try next variation or fallback to RAG
                    else:
                        logger.info(f"DB result matches expected course {expected_dept} {expected_number}")
                
                results['db_results'] = db_result
                results['source'] = 'database'
                results['found'] = True
                logger.info(f"DB search found results on attempt {i+1}")
                break
                
    except Exception as e:
        logger.warning(f"DB search failed: {e}")
    
    # Step 2: ALWAYS try RAG search for course queries (to supplement DB results)
    # or if DB didn't find results
    if search_type == "course" or not results['found']:
        try:
            pdf_service = get_pdf_vector_service()
            
            for i, q_var in enumerate(query_variations[:max_retries]):
                logger.info(f"RAG search attempt {i+1}/{max_retries}: '{q_var}'")
                
                # For course searches, also try cross-department variations
                search_queries = [q_var]
                if search_type == "course":
                    search_queries.extend(_get_cross_dept_queries(q_var))
                
                for sq in search_queries[:5]:
                    rag_results = pdf_service.search(sq, top_k=5)
                    
                    if rag_results and len(rag_results) > 0:
                        # Check if results are relevant (score > 0.5)
                        top_score = rag_results[0].get('score', 0)
                        if top_score > 0.5:
                            results['rag_results'] = rag_results
                            
                            # For course searches, compare RAG vs DB results
                            # If RAG has exact course code match and DB doesn't, prefer RAG
                            if search_type == "course" and expected_dept and expected_number:
                                rag_top = rag_results[0]
                                rag_code = rag_top.get('metadata', {}).get('course_code', '')
                                expected_code = f"{expected_dept} {expected_number}"
                                
                                # Check if RAG result contains exact course code
                                rag_has_exact = (expected_code in rag_code) or (expected_dept in rag_code and expected_number in rag_code)
                                
                                # Check if DB result contains exact course code
                                db_has_exact = results['db_results'] and (expected_code in results['db_results'].upper() or
                                              (expected_dept in results['db_results'].upper() and expected_number in results['db_results']))
                                
                                if rag_has_exact and not db_has_exact:
                                    logger.info(f"RAG has exact match for {expected_code}, preferring RAG over DB")
                                    results['source'] = 'rag'
                                    results['db_results'] = None  # Clear DB results to use RAG
                                elif top_score >= 0.9:
                                    # High-confidence RAG result
                                    if not results['db_results']:
                                        results['source'] = 'rag'
                            else:
                                if not results['found']:
                                    results['source'] = 'rag'
                            
                            results['found'] = True
                            logger.info(f"RAG search found results on attempt {i+1} with score {top_score:.2f}")
                            break
                
                if results['rag_results']:
                    break
                    
        except Exception as e:
            logger.warning(f"RAG search failed: {e}")
    
    return results


def _clean_query(query: str) -> str:
    """Remove question words and punctuation from query."""
    clean = query.replace("?", "").replace(":", "").replace(",", "")
    stop_words = ["who", "what", "where", "when", "how", "why", "which",
                  "is", "are", "the", "a", "an", "teaches", "taught", 
                  "tell", "me", "about", "can", "you", "please", "find"]
    for word in stop_words:
        clean = re.sub(rf'\b{word}\b', '', clean, flags=re.IGNORECASE)
    return " ".join(clean.split()).strip()


def _generate_query_variations(query: str, search_type: str) -> List[str]:
    """Generate query variations for retry logic."""
    variations = [query]
    
    # Extract course code if present
    code_match = re.search(r'([A-Z]{2,4})\s*/?([A-Z]{2,4})?\s*(\d{3,4})', query.upper())
    if code_match:
        dept1 = code_match.group(1)
        code = code_match.group(3)
        variations.append(f"{dept1} {code}")
        variations.append(code)  # Just the number
    
    # Add keyword-focused variations
    words = query.split()
    if len(words) > 2:
        # Try first two significant words
        variations.append(" ".join(words[:2]))
        # Try last two significant words
        variations.append(" ".join(words[-2:]))
    
    return variations


def _get_cross_dept_queries(query: str) -> List[str]:
    """Generate cross-department query variations for courses."""
    code_match = re.search(r'([A-Z]{2,4})\s*(\d{3,4})', query.upper())
    if not code_match:
        return []
    
    dept = code_match.group(1)
    code = code_match.group(2)
    
    cross_depts = ['CS', 'DS', 'ECE', 'MA', 'MIS', 'OBC', 'FIN', 'MKT', 'OIE']
    return [f"{d} {code}" for d in cross_depts if d != dept]


def _has_valid_results(result: str) -> bool:
    """Check if result string contains valid data."""
    if not result:
        return False
    negative_indicators = [
        "No courses found",
        "No programs found", 
        "not found",
        "No results",
        "No matching"
    ]
    return not any(ind.lower() in result.lower() for ind in negative_indicators)


def _format_rag_results(results: List[Dict], query: str, search_type: str = "general") -> str:
    """Format RAG results with smart text extraction."""
    if not results:
        return ""
    
    formatted = []
    for i, r in enumerate(results[:5]):
        source = r.get('source', 'Unknown')
        full_text = r.get('text', '')
        score = r.get('score', 0)
        
        # Try to extract the most relevant section
        text = _extract_relevant_section(full_text, query, search_type)
        formatted.append(f"**[{i+1}] From: {source}** (relevance: {score:.2f})\n{text}")
    
    return "\n\n".join(formatted)


def _extract_relevant_section(text: str, query: str, search_type: str) -> str:
    """Extract the most relevant section from text based on query."""
    # Try to find course code position
    code_match = re.search(r'([A-Z]{2,4})\s*(\d{3,4})', query.upper())
    if code_match:
        dept = code_match.group(1)
        code = code_match.group(2)
        
        # Look for the course code in text
        patterns = [
            rf'{dept}\s*{code}',
            rf'{dept}/\w+\s*{code}',
            rf'\w+/{dept}\s*{code}',
        ]
        
        for p in patterns:
            match = re.search(p, text.upper())
            if match:
                pos = match.start()
                start = max(0, pos - 200)
                end = min(len(text), pos + 800)
                excerpt = text[start:end]
                if start > 0:
                    excerpt = "..." + excerpt
                if end < len(text):
                    excerpt = excerpt + "..."
                return excerpt
    
    # Default: return first 1000 chars
    return text[:1000] + ("..." if len(text) > 1000 else "")


# Tool 1: Student context lookup
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


def smart_course_search_tool(query: str) -> str:
    """
    Smart course search using unified search strategy.
    
    Search for course information:
    - Who teaches a course?
    - Course descriptions, prerequisites, credits
    - Finding courses by topic or code
    
    Strategy: DB first (2-3 attempts) → RAG fallback (2-3 attempts)
    """
    logger.info(f"Smart course search invoked for: {query}")
    
    # Use unified search with course-specific settings
    result = unified_search(query, search_type="course", max_retries=3)
    
    output_parts = []
    
    if result['db_results']:
        output_parts.append("=== DATABASE RESULTS ===")
        output_parts.append(result['db_results'])
    
    if result['rag_results']:
        output_parts.append("\n=== PDF CATALOG CONTEXT ===")
        formatted_rag = _format_rag_results(result['rag_results'], query, "course")
        output_parts.append(formatted_rag)
    
    if output_parts:
        return "\n".join(output_parts)
    else:
        return f"No course information found for: {query}. Try different keywords."


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


def semantic_search_tool(query: str) -> str:
    """
    General semantic search across academic PDF documents.
    
    This is the FALLBACK tool when specific tools don't find results.
    Uses unified search strategy: tries multiple query variations.
    
    Searches: Bus-school courses, Graduate Business programs, Math courses, CS courses.
    """
    logger.info(f"Semantic search tool invoked for: {query}")
    
    # Use unified search for general queries
    result = unified_search(query, search_type="general", max_retries=2)
    
    if result['rag_results']:
        formatted = _format_rag_results(result['rag_results'], query, "general")
        return f"Found relevant sections:\n\n{formatted}"
    elif result['db_results']:
        return result['db_results']
    else:
        return f"No relevant information found for: {query}"


def program_search_tool(query: str) -> str:
    """
    Search for program/degree information using unified search strategy.
    
    Best for:
    - Program requirements (MBA, MSIT, MSBA, etc.)
    - Specialties and concentrations
    - Degree structure and options
    
    Strategy: DB first → RAG fallback with retry logic.
    """
    logger.info(f"Program search tool invoked for: {query}")
    
    result = unified_search(query, search_type="program", max_retries=3)
    
    output_parts = []
    
    if result['db_results']:
        output_parts.append("=== PROGRAM DATABASE ===")
        output_parts.append(result['db_results'])
    
    if result['rag_results']:
        output_parts.append("\n=== CATALOG DETAILS ===")
        formatted_rag = _format_rag_results(result['rag_results'], query, "program")
        output_parts.append(formatted_rag)
    
    if output_parts:
        return "\n".join(output_parts)
    else:
        return f"No program information found for: {query}. Try 'MBA', 'MSIT', 'MSBA', etc."


# NOTE: course_search_tool has been removed - use smart_course_search_tool instead
# which uses the unified_search layer with DB-first strategy


def pdf_context_tool(query: str) -> str:
    """
    Get comprehensive context from academic PDF documents for a query.
    
    Returns longer, concatenated relevant sections that can be used
    to provide detailed answers about programs, courses, and requirements.
    
    Best for complex questions needing more context from multiple sources.
    """
    try:
        from ..services.pdf_vector_service import get_pdf_vector_service
        
        logger.info(f"PDF context tool invoked for: {query}")
        service = get_pdf_vector_service()
        return service.get_context_for_query(query, max_context_length=4000)
    except Exception as exc:
        logger.error("Error in PDF context tool: %s", exc)
        return f"PDF context retrieval failed: {exc}"


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

SMART_COURSE_SEARCH_TOOL = Tool(
    name="smart_course_search",
    func=smart_course_search_tool,
    description=(
        "PRIMARY tool for course questions. Searches DB first (has instructor, credits, schedule), "
        "then PDF catalogs for descriptions. Best for: 'Who teaches X?', 'What is course X about?', "
        "'Course prerequisites', 'Find courses on topic Y'. Input: course name, code, or topic."
    )
)

DEGREE_PROGRESS_TOOL = Tool(
    name="degree_progress",
    func=degree_progress_tool,
    description=(
        "Compare student's transcript against program requirements. "
        "Shows: which specialties are complete, remaining courses needed, graduation status. "
        "REQUIRES uploaded transcript. Input: program name (e.g., 'MBA', 'MSIT', 'MSBA'). "
        "Best for: 'How close am I to graduating?', 'What do I still need for MBA?'"
    )
)

SEMANTIC_SEARCH_TOOL = Tool(
    name="semantic_search",
    func=semantic_search_tool,
    description=(
        "General semantic search across academic PDF documents. "
        "FALLBACK tool when specific tools don't find results. "
        "Uses unified search with retry logic. "
        "Input: natural language query."
    )
)

PROGRAM_SEARCH_TOOL = Tool(
    name="program_search",
    func=program_search_tool,
    description=(
        "Search for program/degree information (MBA, MSIT, MSBA, etc.). "
        "Uses DB-first strategy with RAG fallback. "
        "Best for: program requirements, specialties, degree structure. "
        "Input: program name or keyword."
    )
)

PDF_CONTEXT_TOOL = Tool(
    name="pdf_context",
    func=pdf_context_tool,
    description=(
        "Get comprehensive context from academic PDFs for complex questions. "
        "Returns longer, concatenated sections from multiple sources. "
        "Best for: detailed program requirements, comparing options, in-depth analysis. "
        "Input: detailed question needing extensive context."
    )
)


def get_all_tools() -> List[Tool]:
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
