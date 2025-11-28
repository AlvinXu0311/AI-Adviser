"""SQLite access layer for the Business School program database."""
from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class ProgramDatabaseService:
    """Helper that exposes structured program/specialty information."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        if not os.path.exists(self.db_path):
            logger.warning(
                "Business School DB not found at %s. Run create_database.py to generate it.",
                self.db_path,
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _extract_program_keywords(self, query: str) -> List[str]:
        """Extract program identifiers (MSIT, MSBA, MSM) from query."""
        query_upper = query.upper()
        keywords = []

        # Known program codes
        program_codes = ["MSIT", "MSBA", "MSM"]
        for code in program_codes:
            if code in query_upper:
                keywords.append(code)

        # If no program codes found, look for keywords that indicate programs
        if not keywords:
            program_keywords = {
                "INFORMATION TECHNOLOGY": "MSIT",
                "BUSINESS ANALYTICS": "MSBA",
                "MANAGEMENT": "MSM",
                "IT": "MSIT",
                "DATA": "MSBA",
            }

            for keyword, code in program_keywords.items():
                if keyword in query_upper:
                    keywords.append(code)

        return keywords

    def program_snapshot(self, query: str, max_programs: int = 2) -> Dict[str, Any]:
        if not os.path.exists(self.db_path):
            return {
                "error": (
                    "Business School database missing. Please ensure bus_school.db exists "
                    "(database/database_project) or set BUS_SCHOOL_DB_PATH."
                )
            }

        # Extract relevant program keywords from the query
        keywords = self._extract_program_keywords(query)

        # If no specific keywords found, return all programs
        if not keywords:
            keywords = ["%"]  # Wildcard to get all programs

        logger.debug(f"Extracted program keywords from query: {keywords}")

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Build query to match extracted keywords
            programs = []
            for keyword in keywords:
                pattern = f"%{keyword}%"
                cur.execute(
                    """
                    SELECT id, program_name, program_code, program_type, program_level,
                           description, Requirements
                    FROM programs
                    WHERE program_name LIKE ? OR program_code LIKE ?
                    ORDER BY program_name
                    LIMIT ?
                    """,
                    (pattern, pattern, max_programs),
                )
                programs.extend(cur.fetchall())

            # Remove duplicates while preserving order
            seen = set()
            unique_programs = []
            for prog in programs:
                if prog["id"] not in seen:
                    seen.add(prog["id"])
                    unique_programs.append(prog)

            if not unique_programs:
                return {"programs": []}

            payload: List[Dict[str, Any]] = []
            for program in unique_programs:
                cur.execute(
                    """
                    SELECT s.id, s.specialty_name, s.description, s.Requirements,
                           sc.is_required, c.course_code, c.Course_Title, c.Subject,
                           c.Credits
                    FROM specialties s
                    LEFT JOIN specialty_classes sc ON sc.specialty_id = s.id
                    LEFT JOIN courses c ON c.course_code = sc.course_code
                    WHERE s.program_id = ?
                    ORDER BY s.specialty_name, sc.is_required DESC, c.Course_Title
                    """,
                    (program["id"],),
                )
                rows = cur.fetchall()
                specialties: Dict[str, Dict[str, Any]] = defaultdict(
                    lambda: {"description": None, "requirements": 0, "required": [], "optional": []}
                )

                for row in rows:
                    spec_name = row["specialty_name"] or "(Unassigned)"
                    spec = specialties[spec_name]
                    spec["description"] = row["description"]
                    spec["requirements"] = row["Requirements"]
                    if row["course_code"]:
                        course_info = {
                            "code": row["course_code"],
                            "title": row["Course_Title"],
                            "subject": row["Subject"],
                            "credits": row["Credits"],
                        }
                        bucket = "required" if row["is_required"] else "optional"
                        spec[bucket].append(course_info)

                payload.append(
                    {
                        "program": program["program_name"],
                        "code": program["program_code"],
                        "level": program["program_level"],
                        "type": program["program_type"],
                        "description": program["description"],
                        "optional_specialties_required": program["Requirements"],
                        "specialties": specialties,
                    }
                )

            return {"programs": payload}

    def search_courses(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search courses by title, code, subject, or description."""
        if not os.path.exists(self.db_path):
            return []

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Search in course title, code, subject, and description
            pattern = f"%{query}%"
            cur.execute(
                """
                SELECT course_code, Course_Title, Course_Description, Subject,
                       Credits, Instructors, Locations, Delivery_Mode, 
                       Academic_Level, Offering_Period
                FROM courses
                WHERE Course_Title LIKE ? 
                   OR course_code LIKE ? 
                   OR Subject LIKE ?
                   OR Course_Description LIKE ?
                ORDER BY Course_Title
                LIMIT ?
                """,
                (pattern, pattern, pattern, pattern, max_results),
            )
            rows = cur.fetchall()

            return [
                {
                    "code": row["course_code"],
                    "title": row["Course_Title"],
                    "description": row["Course_Description"],
                    "subject": row["Subject"],
                    "credits": row["Credits"],
                    "instructors": row["Instructors"],
                    "locations": row["Locations"],
                    "delivery_mode": row["Delivery_Mode"],
                    "academic_level": row["Academic_Level"],
                    "offering_period": row["Offering_Period"],
                }
                for row in rows
            ]

    def summarize_courses(self, query: str) -> str:
        """Format course search results as readable text."""
        courses = self.search_courses(query, max_results=5)

        if not courses:
            return f"No courses found matching '{query}'."

        lines: List[str] = []
        for course in courses:
            lines.append(f"COURSE: {course['code']} - {course['title']}")
            lines.append(f"  Credits: {course['credits'] or 'N/A'}")
            if course['instructors']:
                lines.append(f"  Instructor(s): {course['instructors']}")
            if course['subject']:
                lines.append(f"  Subject: {course['subject']}")
            if course['delivery_mode']:
                lines.append(f"  Delivery: {course['delivery_mode']}")
            if course['locations']:
                lines.append(f"  Location(s): {course['locations']}")
            if course['description']:
                # Truncate long descriptions
                desc = course['description'][:300] + "..." if len(course['description'] or "") > 300 else course['description']
                lines.append(f"  Description: {desc}")
            lines.append("")

        return "\n".join(lines).strip()

    def summarize_programs(self, query: str) -> str:
        # First, check if this looks like a course-related query
        course_keywords = ["course", "class", "teach", "instructor", "professor", "who teaches", "taught by", "credits", "description"]
        is_course_query = any(kw in query.lower() for kw in course_keywords)

        # Also check for course code patterns (e.g., "MIS 500", "BUS 2080")
        import re
        course_code_pattern = re.search(r'\b[A-Z]{2,4}\s*\d{3,4}\b', query.upper())

        if is_course_query or course_code_pattern:
            # Extract the search term - use course code if found, otherwise extract key terms
            if course_code_pattern:
                search_term = course_code_pattern.group()
            else:
                # Remove common words and search for remaining terms
                search_term = query.lower()
                for word in ["who", "teaches", "the", "course", "class", "what", "is", "about", "for", "business"]:
                    search_term = search_term.replace(word, "")
                search_term = search_term.strip()

            course_results = self.summarize_courses(search_term)
            if "No courses found" not in course_results:
                return course_results

        # Try course search first if query contains specific course-related terms
        # This catches queries like "Data Mining" that might be in course titles/descriptions
        course_results = self.summarize_courses(query)
        if "No courses found" not in course_results:
            return course_results

        # Fall back to program search
        snapshot = self.program_snapshot(query, max_programs=2)
        if "error" in snapshot:
            return snapshot["error"]

        programs = snapshot.get("programs", [])
        if not programs:
            return "No program or course in the Business School database matched that description."

        lines: List[str] = []
        for program in programs:
            lines.append(
                f"PROGRAM: {program['program']} (Type: {program['type'] or 'N/A'}, Level: {program['level'] or 'N/A'})"
            )
            lines.append(f"- Optional specialties required: {program['optional_specialties_required']}")
            if program.get("description"):
                lines.append(f"- Overview: {program['description']}")

            for spec_name, spec_data in program["specialties"].items():
                lines.append(
                    f"  • Specialty: {spec_name} (needs {spec_data['requirements']} optional course(s))"
                )
                if spec_data.get("description"):
                    lines.append(f"    Description: {spec_data['description']}")

                required_courses = ", ".join(
                    [f"{c['subject'] or c['code']} ({c['credits']} cr)" for c in spec_data["required"][:5]]
                )
                optional_courses = ", ".join(
                    [f"{c['subject'] or c['code']} ({c['credits']} cr)" for c in spec_data["optional"][:5]]
                )

                if required_courses:
                    lines.append(f"    Required: {required_courses}")
                if optional_courses:
                    lines.append(f"    Optional: {optional_courses}")

            lines.append("")

        return "\n".join(lines).strip()


_db_service: ProgramDatabaseService | None = None


def get_program_db_service() -> ProgramDatabaseService:
    global _db_service
    if _db_service is None:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        default_path = os.path.join(repo_root, "database", "database_project", "bus_school.db")
        db_path = os.getenv("BUS_SCHOOL_DB_PATH", default_path)
        _db_service = ProgramDatabaseService(db_path)
    return _db_service
