"""
RAG (Retrieval-Augmented Generation) Service for knowledge base retrieval.
Provides BM25-based search over program information, courses, and specializations.
"""
import json
import logging
import os
from typing import Dict, List, Any, Optional
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class RAGService:
    """
    RAG service for retrieving relevant program information from knowledge base.
    Uses BM25 algorithm for efficient keyword-based search.
    """

    def __init__(self):
        """Initialize RAG service with knowledge base and BM25 indexing"""
        self.knowledge_base = self._load_knowledge_base()
        self.documents = self._build_documents()
        self.bm25 = self._build_bm25_index()
        logger.info(f"RAG Service initialized with {len(self.documents)} documents")

    def _load_knowledge_base(self) -> Dict[str, Any]:
        """Load program information from knowledge base JSON"""
        try:
            # Find the knowledge base file
            kb_path = os.path.join(
                os.path.dirname(__file__),
                "../knowledge_base/programs.json"
            )

            if not os.path.exists(kb_path):
                # Fallback: try from current directory
                kb_path = "backend/app/knowledge_base/programs.json"

            if not os.path.exists(kb_path):
                logger.warning(f"Knowledge base not found at {kb_path}")
                return {"programs": []}

            with open(kb_path, 'r') as f:
                kb = json.load(f)

            logger.info(f"Loaded knowledge base with {len(kb.get('programs', []))} programs")
            return kb
        except Exception as e:
            logger.error(f"Error loading knowledge base: {str(e)}")
            return {"programs": []}

    def _build_documents(self) -> List[Dict[str, Any]]:
        """Build searchable documents from knowledge base"""
        documents = []

        # Process each program
        for program in self.knowledge_base.get("programs", []):
            program_id = program.get("id", "")
            program_name = program.get("name", "")

            # Add program overview document
            if program.get("overview"):
                documents.append({
                    "type": "program_overview",
                    "program_id": program_id,
                    "program_name": program_name,
                    "text": f"{program_name}. {program.get('overview', '')}",
                    "metadata": {
                        "credits": program.get("total_credits"),
                        "duration": program.get("duration_semester"),
                        "format": program.get("format", [])
                    }
                })

            # Add core courses as documents
            for course in program.get("core_courses", []):
                course_code = course.get("code", "")
                course_name = course.get("name", "")
                documents.append({
                    "type": "course",
                    "program_id": program_id,
                    "program_name": program_name,
                    "text": f"{course_code} {course_name}. {course.get('description', '')}",
                    "metadata": {
                        "course_code": course_code,
                        "course_name": course_name,
                        "credits": course.get("credits"),
                        "required": course.get("required", False),
                        "skills": course.get("skills", [])
                    }
                })

            # Add specializations
            for spec in program.get("specializations", []):
                spec_name = spec.get("name", "")
                documents.append({
                    "type": "specialization",
                    "program_id": program_id,
                    "program_name": program_name,
                    "text": f"{spec_name} Specialization. {spec.get('description', '')}",
                    "metadata": {
                        "specialization": spec_name,
                        "courses": spec.get("required_courses", [])
                    }
                })

            # Add prerequisites
            if program.get("prerequisites"):
                prereq_text = json.dumps(program.get("prerequisites"))
                documents.append({
                    "type": "prerequisites",
                    "program_id": program_id,
                    "program_name": program_name,
                    "text": f"Requirements and prerequisites for {program_name}. {prereq_text}",
                    "metadata": program.get("prerequisites", {})
                })

        logger.info(f"Built {len(documents)} searchable documents")
        return documents

    def _build_bm25_index(self) -> BM25Okapi:
        """Build BM25 index from documents"""
        try:
            # Tokenize documents with better handling of stop words
            tokenized_docs = []
            stop_words = {
                'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be',
                'what', 'when', 'where', 'why', 'how', 'tell', 'me', 'about',
                'you', 'i', 'we', 'they', 'he', 'she', 'it', 'this', 'that',
                'which', 'who', 'whom', 'all', 'each', 'every', 'both', 'few',
                'more', 'most', 'some', 'any', 'do', 'does', 'did', 'have', 'has'
            }

            for doc in self.documents:
                # Tokenize and filter out stop words and very short tokens
                tokens = [
                    token for token in doc["text"].lower().split()
                    if token not in stop_words and len(token) > 2
                ]
                # Always include at least key words even if short (like "IT", "MS")
                tokens.extend([
                    token for token in doc["text"].lower().split()
                    if token in ['it', 'ms', 'ba', 'is'] and len(token) <= 2
                ])
                tokenized_docs.append(tokens)

            bm25 = BM25Okapi(tokenized_docs)
            logger.info(f"BM25 index built successfully with {len(tokenized_docs)} documents")
            return bm25
        except Exception as e:
            logger.error(f"Error building BM25 index: {str(e)}")
            return None

    def _detect_query_intent(self, query: str) -> dict:
        """
        Detect whether query is about graduation requirements vs prerequisites/admission.

        Returns dict with intent analysis:
        - graduation_focus: True if asking about courses to take
        - admission_focus: True if asking about admission criteria
        - emphasize_courses: Boost for core_courses type
        - emphasize_prerequisites: Boost for prerequisites type
        - force_course_search: If True, force inclusion of courses even with low scores
        """
        query_lower = query.lower()

        # Keywords indicating graduation/course requirements
        graduation_keywords = {
            'graduate', 'graduation', 'complete', 'completing', 'finish',
            'finishing', 'earn', 'degree', 'core', 'core courses', 'core course',
            'take', 'courses to take', 'must take', 'required courses',
            'graduation requirement', 'required to graduate', 'required to complete'
        }

        # Keywords indicating prerequisites/admission
        admission_keywords = {
            'prerequisite', 'prerequisites', 'enrollment', 'enroll', 'admission',
            'apply', 'application', 'admitted', 'requirement to enroll',
            'requirement to apply', 'before enrollment', 'before applying'
        }

        graduation_count = sum(1 for kw in graduation_keywords if kw in query_lower)
        admission_count = sum(1 for kw in admission_keywords if kw in query_lower)

        # Check if query is asking about "requirements" in a graduation context
        # (i.e., has graduation keywords or asks about program requirements without admission context)
        has_graduation_keywords = graduation_count > 0
        has_admission_keywords = admission_count > 0

        # "graduation requirements" should be treated as graduation context
        is_graduation_context = has_graduation_keywords or (
            'requirements' in query_lower and 'enrollment' not in query_lower and
            'admission' not in query_lower and 'prerequisite' not in query_lower
        )

        return {
            'graduation_focus': is_graduation_context,
            'admission_focus': has_admission_keywords and graduation_count == 0,
            'emphasize_courses': 300 if is_graduation_context else 0,
            'emphasize_prerequisites': 300 if (has_admission_keywords and graduation_count == 0) else 0,
            'force_course_search': is_graduation_context,  # Force inclusion of courses
            'graduation_count': graduation_count,
            'admission_count': admission_count
        }

    def get_context_for_query(
        self,
        query: str,
        program_id: str = "msit",
        top_k: int = 5,
        use_bm25: bool = True
    ) -> str:
        """
        Retrieve relevant context for a query using BM25 search.
        Prioritizes program-specific results and removes duplicates.
        Intelligently distinguishes between graduation requirements (courses) and prerequisites (admission).

        Args:
            query: User's question
            program_id: Program to prioritize in search
            top_k: Number of top results to return
            use_bm25: Whether to use BM25 ranking (vs simple filtering)

        Returns:
            Formatted context string with relevant information
        """
        try:
            logger.info(f"RAG query: {query[:50]}... (program: {program_id}, top_k: {top_k})")

            if not self.bm25 or not self.documents:
                logger.warning("RAG index not available")
                return ""

            # Detect query intent to prioritize correct requirement type
            intent = self._detect_query_intent(query)
            logger.info(f"Query intent: graduation={intent['graduation_focus']}, admission={intent['admission_focus']}")

            # Tokenize query with same stop word filtering as documents
            stop_words = {
                'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be',
                'what', 'when', 'where', 'why', 'how', 'tell', 'me', 'about',
                'you', 'i', 'we', 'they', 'he', 'she', 'it', 'this', 'that',
                'which', 'who', 'whom', 'all', 'each', 'every', 'both', 'few',
                'more', 'most', 'some', 'any', 'do', 'does', 'did', 'have', 'has'
            }
            query_tokens = [
                token for token in query.lower().split()
                if token not in stop_words and len(token) > 2
            ]
            # Always include key acronyms/short words
            query_tokens.extend([
                token for token in query.lower().split()
                if token in ['it', 'ms', 'ba', 'is'] and len(token) <= 2
            ])

            logger.info(f"Query tokens after filtering: {query_tokens}")

            # Get BM25 scores
            scores = self.bm25.get_scores(query_tokens)

            # Rank documents by score, with smart type boosting based on query intent
            def sort_key(idx):
                doc = self.documents[idx]
                score = scores[idx]
                doc_type = doc.get("type", "")
                doc_program = doc.get("program_id", "")

                # Apply score boost if from target program
                program_boost = 1000 if doc_program == program_id else 0

                # Apply type priority with query-intent-aware boosting
                type_priority = {
                    "course": 100,
                    "prerequisites": 50,
                    "program_overview": 30,
                    "specialization": 10,
                    "unknown": 0
                }
                type_boost = type_priority.get(doc_type, 0)

                # Add intent-based emphasis
                # If query is about graduation, significantly boost course documents
                if intent['graduation_focus'] and doc_type == "course":
                    type_boost += intent['emphasize_courses']

                # If query is about admission/prerequisites, boost prerequisites
                if intent['admission_focus'] and doc_type == "prerequisites":
                    type_boost += intent['emphasize_prerequisites']

                # If score is 0 but it's a course from target program, give it a baseline score
                # This ensures all courses are included even if query doesn't mention their keywords
                if score == 0 and doc_type == "course" and doc_program == program_id:
                    score = 0.1  # Small baseline score so courses get included

                return (program_boost + type_boost, score)

            ranked_indices = sorted(range(len(scores)), key=sort_key, reverse=True)

            # Track seen documents to avoid duplicates
            seen_docs = set()
            results = []

            for idx in ranked_indices:
                if len(results) >= top_k:
                    break

                doc = self.documents[idx]

                # Skip if we've already added this course/document
                doc_type = doc.get("type", "")
                if doc_type == "course":
                    doc_key = (doc_type, doc.get("metadata", {}).get("course_code", ""))
                elif doc_type == "prerequisites":
                    doc_key = (doc_type, doc.get("program_id", ""))
                else:
                    doc_key = (doc_type, doc.get("program_id", ""))

                if doc_key in seen_docs:
                    logger.debug(f"Skipping duplicate: {doc_key}")
                    continue

                seen_docs.add(doc_key)

                # Include document if:
                # 1. It has relevance score > 0, OR
                # 2. It's a course from target program and query is graduation-focused (force_course_search)
                is_course_from_target = (doc_type == "course" and doc.get("program_id") == program_id)
                should_include_zero_score = is_course_from_target and intent.get('force_course_search', False)

                if scores[idx] > 0 or should_include_zero_score:
                    results.append(doc)
                else:
                    logger.debug(f"Skipping low-score document: {scores[idx]}")

            if not results:
                logger.warning(f"No relevant documents found for query: {query[:50]}, providing program overview as fallback")
                # Fallback: return program overview if no results
                for program in self.knowledge_base.get("programs", []):
                    if program.get("id") == program_id:
                        overview = program.get("overview", "")
                        if overview:
                            return f"Program Information:\n{program.get('name', '')} - {overview}"
                return "No relevant information found."

            # Format results
            context_parts = []

            # Separate by program first, prioritize target program
            primary_docs = [d for d in results if d.get("program_id") == program_id]
            secondary_docs = [d for d in results if d.get("program_id") != program_id]

            all_results = primary_docs + secondary_docs

            # Group by type for better organization
            by_type = {}
            for doc in all_results:
                doc_type = doc.get("type", "unknown")
                if doc_type not in by_type:
                    by_type[doc_type] = []
                by_type[doc_type].append(doc)

            # Format by type, with program-specific focus
            target_program_name = None
            for program in self.knowledge_base.get("programs", []):
                if program.get("id") == program_id:
                    target_program_name = program.get("name", "")
                    break

            if "program_overview" in by_type:
                # Only show target program overview
                target_overview = [d for d in by_type["program_overview"] if d.get("program_id") == program_id]
                if target_overview:
                    context_parts.append(f"PROGRAM INFORMATION ({program_id.upper()}):")
                    for doc in target_overview:
                        context_parts.append(f"  {doc['text']}")

            if "course" in by_type:
                context_parts.append("\nCORE COURSES:")
                course_added = set()
                for doc in by_type["course"]:
                    metadata = doc.get("metadata", {})
                    code = metadata.get("course_code", "")

                    # Skip if already added
                    if code in course_added:
                        continue
                    course_added.add(code)

                    # Prioritize target program courses
                    is_target = doc.get("program_id") == program_id
                    marker = "[Target Program] " if is_target else ""

                    name = metadata.get("course_name", "")
                    credits = metadata.get("credits", "")
                    context_parts.append(f"  • {marker}{code}: {name} ({credits} credits)")
                    if metadata.get("skills"):
                        context_parts.append(f"    Skills: {', '.join(metadata['skills'])}")

            if "specialization" in by_type:
                context_parts.append("\nSPECIALIZATIONS:")
                for doc in by_type["specialization"]:
                    context_parts.append(f"  • {doc['text']}")

            if "prerequisites" in by_type:
                context_parts.append(f"\nPREREQUISITES for {program_id.upper()}:")
                # Only show target program prerequisites
                target_prereqs = [d for d in by_type["prerequisites"] if d.get("program_id") == program_id]
                for doc in target_prereqs:
                    prereq_data = doc.get("metadata", {})
                    context_parts.append(f"  • Bachelor's degree required")
                    if "programming_courses" in prereq_data:
                        context_parts.append(f"  • {prereq_data['programming_courses']}")
                    if "math_requirement" in prereq_data:
                        context_parts.append(f"  • {prereq_data['math_requirement']}")

            context = "\n".join(context_parts)
            logger.info(f"RAG retrieved {len(results)} documents ({len(primary_docs)} primary, {len(secondary_docs)} secondary), {len(context)} chars")

            return context

        except Exception as e:
            logger.error(f"Error in RAG retrieval: {str(e)}")
            return ""

    def get_program_overview(self, program_id: str = "msit") -> str:
        """Get overview of a specific program"""
        try:
            for program in self.knowledge_base.get("programs", []):
                if program.get("id") == program_id:
                    overview = program.get("overview", "")
                    credits = program.get("total_credits", "")
                    duration = program.get("duration_semester", "")

                    return f"""
{program.get('name', '')}
{'=' * 50}
Overview: {overview}
Total Credits: {credits}
Duration: {duration}
"""

            return f"Program {program_id} not found."
        except Exception as e:
            logger.error(f"Error getting program overview: {str(e)}")
            return ""

    def get_course_details(self, course_code: str, program_id: str = "msit") -> str:
        """Get detailed information about a specific course"""
        try:
            for program in self.knowledge_base.get("programs", []):
                if program.get("id") == program_id:
                    for course in program.get("core_courses", []):
                        if course.get("code") == course_code:
                            details = f"""
Course: {course.get('code')} - {course.get('name')}
{'=' * 50}
Credits: {course.get('credits')}
Description: {course.get('description', '')}
Skills: {', '.join(course.get('skills', []))}
Difficulty: {course.get('difficulty', 'N/A')}
Workload: {course.get('workload', 'N/A')}
"""
                            return details

            return f"Course {course_code} not found in program {program_id}."
        except Exception as e:
            logger.error(f"Error getting course details: {str(e)}")
            return ""

    def get_specializations(self, program_id: str = "msit") -> str:
        """Get available specializations for a program"""
        try:
            for program in self.knowledge_base.get("programs", []):
                if program.get("id") == program_id:
                    specs = program.get("specializations", [])
                    if not specs:
                        return f"No specializations available for {program.get('name', '')}"

                    result = f"Specializations for {program.get('name', '')}:\n"
                    for spec in specs:
                        result += f"\n• {spec.get('name', '')}\n"
                        result += f"  Description: {spec.get('description', '')}\n"
                        courses = spec.get("required_courses", [])
                        if courses:
                            result += f"  Required Courses: {', '.join(courses)}\n"

                    return result

            return f"Program {program_id} not found."
        except Exception as e:
            logger.error(f"Error getting specializations: {str(e)}")
            return ""


# Singleton instance
_rag_service = None


def get_rag_service() -> RAGService:
    """Get or create the RAG service"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
