"""
RAG (Retrieval-Augmented Generation) Service for program-related questions.
Provides local knowledge base retrieval without API calls.
"""
import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path


class RAGService:
    """Service for retrieving program information from knowledge base"""

    def __init__(self):
        """Initialize RAG service with knowledge base"""
        self.knowledge_base = {}
        self.programs = {}
        self.load_knowledge_base()
        print("[RAG Service] Initialized with local knowledge base")

    def load_knowledge_base(self) -> None:
        """Load knowledge base from JSON files"""
        try:
            kb_path = Path(__file__).parent.parent / "knowledge_base"

            # Load programs
            programs_file = kb_path / "programs.json"
            if programs_file.exists():
                with open(programs_file, "r") as f:
                    data = json.load(f)
                    for program in data.get("programs", []):
                        self.programs[program["id"]] = program
                print(f"[RAG] Loaded {len(self.programs)} programs")
            else:
                print(f"[WARNING] [RAG] Programs file not found: {programs_file}")

        except Exception as e:
            print(f"[ERROR] [RAG] Error loading knowledge base: {str(e)}")

    def retrieve_program_info(self, program_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve complete program information.

        Args:
            program_id: Program identifier (e.g., 'msit')

        Returns:
            Program information dict or None
        """
        return self.programs.get(program_id)

    def search_by_keyword(self, query: str, program_id: str = "msit") -> List[Dict[str, Any]]:
        """
        Search program information by keyword.

        Args:
            query: Search query
            program_id: Program to search in

        Returns:
            List of relevant information chunks
        """
        results = []
        program = self.programs.get(program_id)
        if not program:
            return results

        query_lower = query.lower()
        results_dict = {}

        # Search in program overview
        if query_lower in program.get("overview", "").lower():
            results_dict["overview"] = {
                "type": "overview",
                "content": program["overview"]
            }

        # Search in core courses
        for course in program.get("core_courses", []):
            if (query_lower in course.get("name", "").lower() or
                    query_lower in course.get("code", "").lower() or
                    query_lower in course.get("description", "").lower()):
                results_dict[f"core_{course['code']}"] = {
                    "type": "core_course",
                    "code": course["code"],
                    "name": course["name"],
                    "credits": course["credits"],
                    "description": course.get("description", "")
                }

        # Search in specializations
        for spec in program.get("specializations", []):
            if query_lower in spec.get("name", "").lower():
                results_dict[f"spec_{spec['id']}"] = {
                    "type": "specialization",
                    "name": spec["name"],
                    "courses": spec.get("courses", [])  # Keep as full objects with details
                }
            # Search in specialization courses
            for course in spec.get("courses", []):
                if (query_lower in course.get("name", "").lower() or
                        query_lower in course.get("code", "").lower()):
                    # When we find a course, also include its specialization
                    if f"spec_{spec['id']}" not in results_dict:
                        results_dict[f"spec_{spec['id']}"] = {
                            "type": "specialization",
                            "name": spec["name"],
                            "courses": spec.get("courses", [])
                        }
                    # Also add the individual course
                    results_dict[f"spec_course_{course.get('code')}"] = {
                        "type": "specialization_course",
                        "specialization": spec["name"],
                        "code": course.get("code"),
                        "name": course.get("name"),
                        "credits": course.get("credits")
                    }

        # Search in capstone
        capstone = program.get("capstone", {})
        if query_lower in "capstone" or query_lower in str(capstone).lower():
            capstone_info = {
                "type": "capstone",
                "required": capstone.get("required"),
                "credits": capstone.get("credits"),
                "courses": [
                    {
                        "code": c.get('code'),
                        "name": c.get('name'),
                        "credits": c.get('credits')
                    }
                    for c in capstone.get("courses", [])
                ]
            }
            results_dict["capstone"] = capstone_info

        return list(results_dict.values())

    def get_program_requirements(self, program_id: str = "msit") -> Dict[str, Any]:
        """
        Get full program requirements breakdown.

        Args:
            program_id: Program identifier

        Returns:
            Program requirements dictionary
        """
        program = self.programs.get(program_id)
        if not program:
            return {}

        return {
            "program_name": program.get("name"),
            "total_credits": program.get("total_credits"),
            "structure": program.get("program_structure", {}),
            "core_courses": program.get("core_courses", []),
            "specializations_count": len(program.get("specializations", [])),
            "capstone_required": program.get("capstone", {}).get("required"),
            "capstone_credits": program.get("capstone", {}).get("credits")
        }

    def get_course_info(self, course_code: str, program_id: str = "msit") -> Optional[Dict[str, Any]]:
        """
        Get information about a specific course.

        Args:
            course_code: Course code (e.g., 'MIS581')
            program_id: Program identifier

        Returns:
            Course information or None
        """
        program = self.programs.get(program_id)
        if not program:
            return None

        course_code_upper = course_code.upper()

        # Search in core courses
        for course in program.get("core_courses", []):
            if course["code"].upper() == course_code_upper:
                return {
                    "type": "core_course",
                    **course
                }

        # Search in specializations
        for spec in program.get("specializations", []):
            for course in spec.get("courses", []):
                if course.get("code", "").upper() == course_code_upper:
                    return {
                        "type": "specialization_course",
                        "specialization": spec["name"],
                        **course
                    }

        # Search in capstone
        for course in program.get("capstone", {}).get("courses", []):
            if course["code"].upper() == course_code_upper:
                return {
                    "type": "capstone_course",
                    **course
                }

        return None

    def get_specializations(self, program_id: str = "msit") -> List[Dict[str, Any]]:
        """
        Get all available specializations.

        Args:
            program_id: Program identifier

        Returns:
            List of specializations
        """
        program = self.programs.get(program_id)
        if not program:
            return []

        specs = []
        for spec in program.get("specializations", []):
            specs.append({
                "id": spec.get("id"),
                "name": spec.get("name"),
                "course_count": len(spec.get("courses", [])),
                "courses": [
                    {
                        "code": c.get("code"),
                        "name": c.get("name")
                    }
                    for c in spec.get("courses", [])
                ]
            })
        return specs

    def get_context_for_query(self, query: str, program_id: str = "msit", top_k: int = 5) -> str:
        """
        Get relevant context from knowledge base for LLM prompt.

        Args:
            query: User query
            program_id: Program identifier
            top_k: Number of top results to return

        Returns:
            Formatted context string
        """
        # Search for relevant information
        search_results = self.search_by_keyword(query, program_id)

        if not search_results:
            # If no specific results, provide general program info
            program = self.programs.get(program_id)
            if program:
                capstone = program.get('capstone', {})
                capstone_courses = capstone.get('courses', [])
                capstone_course_list = []
                if capstone_courses:
                    for c in capstone_courses:
                        capstone_course_list.append(f"{c.get('code')} ({c.get('credits')} cr)")
                    capstone_description = ", ".join(capstone_course_list)
                else:
                    capstone_description = "OBC505, MIS573"

                core_codes = ", ".join([c.get('code') for c in program.get('core_courses', [])])
                spec_names = ", ".join([s.get('name') for s in program.get('specializations', [])])

                context = f"""
Program Information: {program.get('name')}
Total Credits Required: {program.get('total_credits')}

Program Structure:
- 3 Core Courses (9 credits)
  Core: {core_codes}

- 2 Specializations (18 credits)
  Must choose 2 specializations from: {spec_names}

- Capstone (6 credits) - REQUIRED
  Take 2 courses: {capstone_description}
"""
                return context

        # Format search results
        context = "Relevant Program Information:\n\n"
        for i, result in enumerate(search_results[:top_k], 1):
            result_type = result.get("type", "unknown")

            if result_type == "core_course":
                context += f"{i}. Core Course: {result.get('code')} - {result.get('name')}\n"
                context += f"   Credits: {result.get('credits')}\n"
                if result.get('description'):
                    context += f"   Description: {result.get('description')}\n"

            elif result_type == "specialization":
                context += f"{i}. Specialization: {result.get('name')} (9 credits total)\n"
                courses = result.get('courses', [])
                context += f"   Required courses:\n"
                for course in courses:
                    if isinstance(course, dict):
                        # New format with course details
                        context += f"   - {course.get('code')}: {course.get('name')} ({course.get('credits')} credits)\n"
                    else:
                        # Old format (just string)
                        context += f"   - {course}\n"

            elif result_type == "specialization_course":
                context += f"{i}. {result.get('specialization')} - {result.get('code')}: {result.get('name')}\n"
                context += f"   Credits: {result.get('credits')}\n"

            elif result_type == "capstone":
                context += f"{i}. Capstone Experience (Required - {result.get('credits')} credits total)\n"
                courses = result.get('courses', [])
                if isinstance(courses, list) and len(courses) > 0:
                    if isinstance(courses[0], dict):
                        # New format with course details
                        context += f"   You must take TWO capstone courses:\n"
                        for course in courses:
                            context += f"   - {course.get('code')}: {course.get('name')} ({course.get('credits')} credits)\n"
                    else:
                        # Old format with just course names
                        context += f"   Courses: {', '.join(courses)}\n"
                context += f"   Total: 2 courses = 6 credits\n"

            elif result_type == "overview":
                context += f"{i}. Program Overview:\n"
                context += f"   {result.get('content')}\n"

            context += "\n"

        return context


# Global RAG service instance
_rag_service = None


def get_rag_service() -> RAGService:
    """Get or create global RAG service instance"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
