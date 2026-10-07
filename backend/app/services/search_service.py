"""
Shared retrieval layer for the academic adviser.

Used by both the LangChain ReAct agent (app/agents/tools.py) and the MCP server
(mcp_server/server.py), so the two surfaces always run the same DB-first →
RAG-fallback search logic. Kept free of LangChain imports on purpose.
"""
from typing import List, Dict, Any, Optional, Callable
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
    from .program_db_service import get_program_db_service
    from .pdf_vector_service import get_pdf_vector_service
    
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

def business_school_db_tool(query: str) -> str:
    """Query the authoritative Business School SQLite database for program data."""
    try:
        from .program_db_service import get_program_db_service

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


def pdf_context_tool(query: str) -> str:
    """
    Get comprehensive context from academic PDF documents for a query.
    
    Returns longer, concatenated relevant sections that can be used
    to provide detailed answers about programs, courses, and requirements.
    
    Best for complex questions needing more context from multiple sources.
    """
    try:
        from .pdf_vector_service import get_pdf_vector_service
        
        logger.info(f"PDF context tool invoked for: {query}")
        service = get_pdf_vector_service()
        return service.get_context_for_query(query, max_context_length=4000)
    except Exception as exc:
        logger.error("Error in PDF context tool: %s", exc)
        return f"PDF context retrieval failed: {exc}"
