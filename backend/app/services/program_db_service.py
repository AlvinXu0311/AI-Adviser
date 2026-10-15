"""SQLite access layer for the Business School program database."""
from __future__ import annotations

import os
import sqlite3
from typing import Dict, List, Any, Optional
import logging
import re

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
        """Extract program search terms from query.
        
        Maps abbreviations to actual search terms that match database content.
        """
        query_upper = query.upper()
        query_lower = query.lower()
        keywords = []

        # Map abbreviations/terms to database-matching search patterns
        # Key: trigger patterns, Value: search terms that match DB content
        program_patterns = {
            # MBA programs (most specific term first: "MBA" alone only matches "MBA in Analytics")
            ("MBA", "mba", "business administration"): ["Master of Business Administration", "MBA"],
            # MSBA / Analytics ("Analytics" alone also matches MBA in Analytics and OSCA)
            ("MSBA", "msba", "business analytics", "analytics"): ["Business Analytics", "Analytics"],
            # MSIT / Information Technology
            ("MSIT", "msit", "information technology"): ["Information Technology"],
            # FinTech
            ("fintech", "financial technology", "fin tech"): ["FinTech", "Financial Technology"],
            # Operations & Supply Chain
            ("supply chain", "operations", "OSCA", "osca"): ["Supply Chain", "Operations"],
        }

        for triggers, search_terms in program_patterns.items():
            for trigger in triggers:
                if trigger.upper() in query_upper or trigger.lower() in query_lower:
                    keywords.extend(search_terms)
                    break

        # If no specific program matched, try the raw query words
        if not keywords:
            # Add significant words from query (longer than 3 chars)
            words = [w for w in query.split() if len(w) > 3 and w.lower() not in 
                    ('what', 'about', 'tell', 'show', 'list', 'program', 'programs', 
                     'course', 'courses', 'specialization', 'specializations')]
            keywords.extend(words[:2])  # Take first 2 significant words

        return list(dict.fromkeys(keywords))  # Remove duplicates, keep priority order

    def get_all_programs(self) -> List[Dict[str, Any]]:
        """Get list of all programs with basic info."""
        if not os.path.exists(self.db_path):
            return []

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT id, program_id, program_name, program_code, program_type, 
                       program_level, description, program_notes, program_requirements
                FROM programs
                ORDER BY program_name
            """)
            return [dict(row) for row in cur.fetchall()]

    def program_snapshot(self, query: str, max_programs: int = 3) -> Dict[str, Any]:
        """Get detailed program information matching the query."""
        if not os.path.exists(self.db_path):
            return {
                "error": (
                    "Business School database missing. Please ensure bus_school.db exists "
                    "(database/database_project) or set BUS_SCHOOL_DB_PATH."
                )
            }

        # Extract relevant program keywords from the query
        keywords = self._extract_program_keywords(query)

        logger.debug(f"Extracted program keywords from query: {keywords}")

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Build query to match extracted keywords
            programs = []
            if keywords:
                for keyword in keywords:
                    pattern = f"%{keyword}%"
                    cur.execute(
                        """
                        SELECT id, program_id, program_name, program_code, program_type, 
                               program_level, description, program_notes, program_requirements
                        FROM programs
                        WHERE program_name LIKE ? OR program_code LIKE ? OR description LIKE ?
                        ORDER BY program_name
                        LIMIT ?
                        """,
                        (pattern, pattern, pattern, max_programs),
                    )
                    programs.extend(cur.fetchall())
            else:
                # No specific keywords - get all programs
                cur.execute(
                    """
                    SELECT id, program_id, program_name, program_code, program_type,
                           program_level, description, program_notes, program_requirements
                    FROM programs
                    ORDER BY program_name
                    LIMIT ?
                    """,
                    (max_programs,),
                )
                programs = cur.fetchall()

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
                # Get specialties for this program
                cur.execute(
                    """
                    SELECT id, specialty_id, specialty_name, specialty_type, specialty_notes
                    FROM specialties
                    WHERE program_id = ?
                    ORDER BY specialty_type DESC, specialty_name
                    """,
                    (program["id"],),
                )
                specialty_rows = cur.fetchall()

                specialties: List[Dict[str, Any]] = []
                for spec_row in specialty_rows:
                    # Get sub-specialties for this specialty
                    cur.execute(
                        """
                        SELECT ss.id, ss.sub_specialty_id, ss.sub_specialty_name, 
                               ss.sub_specialty_requirements
                        FROM sub_specialties ss
                        WHERE ss.specialty_id = ?
                        ORDER BY ss.sub_specialty_name
                        """,
                        (spec_row["id"],),
                    )
                    sub_specs = cur.fetchall()

                    sub_specialties: List[Dict[str, Any]] = []
                    for sub_spec in sub_specs:
                        # Get courses for this sub-specialty
                        cur.execute(
                            """
                            SELECT sc.course_code, sc.sub_specialty_courses,
                                   c.Course_Title, c.Credits, c.Subject, c.Course_Description
                            FROM specialty_classes sc
                            LEFT JOIN courses c ON c.course_code = sc.course_code
                            WHERE sc.sub_specialty_id = ?
                            ORDER BY sc.course_code
                            """,
                            (sub_spec["id"],),
                        )
                        course_rows = cur.fetchall()
                        courses = [
                            {
                                "code": row["course_code"],
                                "title": row["Course_Title"] or row["sub_specialty_courses"],
                                "credits": row["Credits"],
                                "subject": row["Subject"],
                            }
                            for row in course_rows
                        ]

                        sub_specialties.append({
                            "name": sub_spec["sub_specialty_name"],
                            "requirements": sub_spec["sub_specialty_requirements"],
                            "courses": courses,
                        })

                    specialties.append({
                        "name": spec_row["specialty_name"],
                        "type": spec_row["specialty_type"],  # Required or Optional
                        "notes": spec_row["specialty_notes"],
                        "sub_specialties": sub_specialties,
                    })

                payload.append({
                    "program": program["program_name"],
                    "code": program["program_code"],
                    "level": program["program_level"],
                    "type": program["program_type"],
                    "description": program["description"],
                    "notes": program["program_notes"],
                    "requirements": program["program_requirements"],
                    "specialties": specialties,
                })

            return {"programs": payload}

    def search_courses(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search courses by title, code, subject, or description."""
        if not os.path.exists(self.db_path):
            return []

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Normalize query - remove extra spaces
            query = query.strip()
            pattern = f"%{query}%"
            
            cur.execute(
                """
                SELECT course_code, Course_Title, Course_Description, Subject,
                       Credits, Instructors, Locations, Delivery_Mode, 
                       Academic_Level, Offering_Period, Instructional_Format,
                       Section_Details, Academic_Units
                FROM courses
                WHERE Course_Title LIKE ? 
                   OR course_code LIKE ? 
                   OR Subject LIKE ?
                   OR Course_Description LIKE ?
                   OR Instructors LIKE ?
                ORDER BY course_code
                LIMIT ?
                """,
                (pattern, pattern, pattern, pattern, pattern, max_results),
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
                    "instructional_format": row["Instructional_Format"],
                    "academic_level": row["Academic_Level"],
                    "offering_period": row["Offering_Period"],
                    "section_details": row["Section_Details"],
                    "academic_units": row["Academic_Units"],
                }
                for row in rows
            ]

    def get_course_by_code(self, course_code: str) -> Optional[Dict[str, Any]]:
        """Get a specific course by its code."""
        if not os.path.exists(self.db_path):
            return None

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # Normalize course code
            course_code = course_code.strip().upper()
            
            cur.execute(
                """
                SELECT course_code, Course_Title, Course_Description, Subject,
                       Credits, Instructors, Locations, Delivery_Mode, 
                       Academic_Level, Offering_Period, Instructional_Format,
                       Section_Details, Academic_Units
                FROM courses
                WHERE UPPER(course_code) = ? OR UPPER(REPLACE(course_code, ' ', '')) = ?
                """,
                (course_code, course_code.replace(' ', '')),
            )
            row = cur.fetchone()
            
            if not row:
                return None
                
            return {
                "code": row["course_code"],
                "title": row["Course_Title"],
                "description": row["Course_Description"],
                "subject": row["Subject"],
                "credits": row["Credits"],
                "instructors": row["Instructors"],
                "locations": row["Locations"],
                "delivery_mode": row["Delivery_Mode"],
                "instructional_format": row["Instructional_Format"],
                "academic_level": row["Academic_Level"],
                "offering_period": row["Offering_Period"],
                "section_details": row["Section_Details"],
                "academic_units": row["Academic_Units"],
            }

    def summarize_courses(self, query: str) -> str:
        """Format course search results as readable text."""
        courses = self.search_courses(query, max_results=8)

        if not courses:
            return f"No courses found matching '{query}'."

        lines: List[str] = []
        for course in courses:
            lines.append(f"COURSE: {course['code']} - {course['title']}")
            if course['credits']:
                lines.append(f"  Credits: {course['credits']}")
            if course['instructors']:
                lines.append(f"  Instructor(s): {course['instructors']}")
            if course['subject']:
                lines.append(f"  Subject: {course['subject']}")
            if course['delivery_mode']:
                lines.append(f"  Delivery: {course['delivery_mode']}")
            if course['instructional_format']:
                lines.append(f"  Format: {course['instructional_format']}")
            if course['locations']:
                lines.append(f"  Location(s): {course['locations']}")
            if course['offering_period']:
                lines.append(f"  Offered: {course['offering_period']}")
            if course['description']:
                desc = course['description'][:400] + "..." if len(course['description'] or "") > 400 else course['description']
                lines.append(f"  Description: {desc}")
            lines.append("")

        return "\n".join(lines).strip()

    def summarize_programs(self, query: str) -> str:
        """Format program/specialty/course information as readable text."""
        # First, check if this looks like a course-related query
        course_keywords = ["course", "class", "teach", "instructor", "professor", 
                          "who teaches", "taught by", "credits", "description",
                          "prerequisite", "prereq"]
        is_course_query = any(kw in query.lower() for kw in course_keywords)

        # Check for instructor/faculty queries - look for names (capitalized words)
        instructor_keywords = ["who is", "who's", "professor", "instructor", "teaches", 
                               "taught by", "dr.", "dr ", "faculty"]
        is_instructor_query = any(kw in query.lower() for kw in instructor_keywords)
        
        # Extract potential name from query (2+ capitalized words together)
        name_pattern = re.search(r'\b([A-Z][a-z]*(?:\s+[A-Z][a-z]*)+)\b', query)
        # Also try to find names like "ZQ Cheng" with initials
        initial_name_pattern = re.search(r'\b([A-Z]{1,2}\s+[A-Z][a-z]+)\b', query)
        
        if is_instructor_query or name_pattern or initial_name_pattern:
            # Extract the name to search
            if initial_name_pattern:
                search_name = initial_name_pattern.group(1)
            elif name_pattern:
                search_name = name_pattern.group(1)
            else:
                # Extract words after "who is" or similar
                for keyword in ["who is", "who's", "professor", "instructor", "dr."]:
                    if keyword in query.lower():
                        idx = query.lower().find(keyword) + len(keyword)
                        search_name = query[idx:].strip().split('?')[0].strip()
                        break
                else:
                    search_name = query
            
            # Search for instructor in courses
            instructor_results = self.search_courses(search_name, max_results=10)
            if instructor_results:
                # Filter to only courses where this person is the instructor
                matching_courses = [c for c in instructor_results 
                                   if c.get('instructors') and search_name.lower() in c['instructors'].lower()]
                if matching_courses:
                    lines = [f"Found {len(matching_courses)} course(s) taught by {search_name}:\n"]
                    for course in matching_courses:
                        lines.append(f"COURSE: {course['code']} - {course['title']}")
                        if course['credits']:
                            lines.append(f"  Credits: {course['credits']}")
                        if course['instructors']:
                            lines.append(f"  Instructor(s): {course['instructors']}")
                        if course['academic_level']:
                            lines.append(f"  Level: {course['academic_level']}")
                        if course['delivery_mode']:
                            lines.append(f"  Delivery: {course['delivery_mode']}")
                        if course['locations']:
                            lines.append(f"  Location: {course['locations']}")
                        if course['offering_period']:
                            lines.append(f"  Offered: {course['offering_period']}")
                        if course['section_details']:
                            lines.append(f"  Schedule: {course['section_details']}")
                        if course['description']:
                            # Clean HTML tags
                            desc = re.sub(r'<[^>]+>', '', course['description'])
                            desc = desc[:300] + "..." if len(desc) > 300 else desc
                            lines.append(f"  Description: {desc}")
                        lines.append("")
                    return "\n".join(lines).strip()

        # Check for course code patterns (e.g., "MIS 500", "BUS 2080", "FIN540")
        course_code_pattern = re.search(r'\b[A-Z]{2,4}\s*\d{3,4}\b', query.upper())

        if is_course_query or course_code_pattern:
            # Extract the search term - use course code if found
            if course_code_pattern:
                search_term = course_code_pattern.group()
                # Try exact match first
                course = self.get_course_by_code(search_term)
                if course:
                    lines = [f"COURSE: {course['code']} - {course['title']}"]
                    if course['credits']:
                        lines.append(f"  Credits: {course['credits']}")
                    if course['instructors']:
                        lines.append(f"  Instructor(s): {course['instructors']}")
                    if course['subject']:
                        lines.append(f"  Subject: {course['subject']}")
                    if course['delivery_mode']:
                        lines.append(f"  Delivery: {course['delivery_mode']}")
                    if course['instructional_format']:
                        lines.append(f"  Format: {course['instructional_format']}")
                    if course['locations']:
                        lines.append(f"  Location(s): {course['locations']}")
                    if course['offering_period']:
                        lines.append(f"  Offered: {course['offering_period']}")
                    if course['description']:
                        lines.append(f"  Description: {course['description']}")
                    return "\n".join(lines)
            else:
                # Remove common words and search for remaining terms
                search_term = query.lower()
                for word in ["who", "teaches", "the", "course", "class", "what", "is", 
                            "about", "for", "business", "tell", "me", "can", "you"]:
                    search_term = search_term.replace(word, "")
                search_term = search_term.strip()

            course_results = self.summarize_courses(search_term)
            if "No courses found" not in course_results:
                return course_results

        # Try course search first if query contains specific terms
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
            lines.append(f"PROGRAM: {program['program']}")
            if program.get('type') or program.get('level'):
                lines.append(f"  Type: {program.get('type', 'N/A')}, Level: {program.get('level', 'N/A')}")
            if program.get("description"):
                lines.append(f"  Overview: {program['description']}")
            
            # Calculate total required and optional courses dynamically
            required_specs = [s for s in program.get("specialties", []) if s.get("type") == "Required"]
            optional_specs = [s for s in program.get("specialties", []) if s.get("type") == "Optional"]
            
            # Calculate total required courses
            total_required_courses = 0
            for spec in required_specs:
                for sub in spec.get("sub_specialties", []):
                    try:
                        total_required_courses += int(sub.get('requirements', 0) or len(sub.get('courses', [])))
                    except (ValueError, TypeError):
                        total_required_courses += len(sub.get('courses', []))
            
            # Calculate course range for optional specialties
            opt_course_counts = []
            for spec in optional_specs:
                spec_total = 0
                for sub in spec.get("sub_specialties", []):
                    try:
                        spec_total += int(sub.get('requirements', 0) or len(sub.get('courses', [])))
                    except (ValueError, TypeError):
                        spec_total += len(sub.get('courses', []))
                if spec_total > 0:
                    opt_course_counts.append(spec_total)
            
            if program.get("requirements"):
                opt_needed = program.get("requirements")
                if opt_course_counts:
                    min_courses = min(opt_course_counts)
                    max_courses = max(opt_course_counts)
                    if min_courses == max_courses:
                        opt_courses_desc = f"{min_courses} courses each"
                    else:
                        opt_courses_desc = f"{min_courses}-{max_courses} courses each"
                else:
                    opt_courses_desc = "varies"
                lines.append(f"  GRADUATION REQUIREMENTS:")
                lines.append(f"    - Required courses: {total_required_courses} total (from {len(required_specs)} required specialties)")
                lines.append(f"    - Optional: Complete {opt_needed} specialties ({opt_courses_desc})")
            if program.get("notes"):
                lines.append(f"  Notes: {program['notes']}")

            if required_specs:
                lines.append("\n  [REQ] REQUIRED SPECIALTIES (must complete ALL):")
                for spec in required_specs:
                    # Calculate total courses needed for this specialty
                    total_courses = sum(
                        int(sub.get('requirements', 0) or len(sub.get('courses', [])))
                        for sub in spec.get("sub_specialties", [])
                    )
                    lines.append(f"    • {spec['name']} ({total_courses} courses total)")
                    if spec.get('notes'):
                        lines.append(f"      Notes: {spec['notes']}")
                    for sub_spec in spec.get("sub_specialties", []):
                        req_text = f" (requires {sub_spec['requirements']} courses)" if sub_spec.get('requirements') else ""
                        lines.append(f"      - {sub_spec['name']}{req_text}")
                        courses = sub_spec.get("courses", [])[:5]
                        if courses:
                            course_list = ", ".join([f"{c['code']}" for c in courses])
                            lines.append(f"        Courses: {course_list}")

            if optional_specs:
                opt_needed = program.get("requirements", "N/A")
                lines.append(f"\n  [OPT] OPTIONAL SPECIALTIES (choose {opt_needed}):")
                for spec in optional_specs:
                    # Calculate total courses needed for this specialty
                    total_courses = sum(
                        int(sub.get('requirements', 0) or len(sub.get('courses', [])))
                        for sub in spec.get("sub_specialties", [])
                    )
                    lines.append(f"    • {spec['name']} ({total_courses} courses to complete)")
                    if spec.get('notes'):
                        lines.append(f"      Notes: {spec['notes']}")
                    for sub_spec in spec.get("sub_specialties", []):
                        req_text = f" (requires {sub_spec['requirements']} courses)" if sub_spec.get('requirements') else ""
                        lines.append(f"      - {sub_spec['name']}{req_text}")
                        courses = sub_spec.get("courses", [])[:5]
                        if courses:
                            course_list = ", ".join([f"{c['code']}" for c in courses])
                            lines.append(f"        Courses: {course_list}")

            lines.append("")

        return "\n".join(lines).strip()

    def get_specialty_info(self, specialty_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a specific specialty."""
        if not os.path.exists(self.db_path):
            return None

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            pattern = f"%{specialty_name}%"
            cur.execute(
                """
                SELECT s.id, s.specialty_name, s.specialty_type, s.specialty_notes,
                       p.program_name
                FROM specialties s
                JOIN programs p ON p.id = s.program_id
                WHERE s.specialty_name LIKE ?
                LIMIT 1
                """,
                (pattern,),
            )
            row = cur.fetchone()
            
            if not row:
                return None
            
            # Get sub-specialties and courses
            cur.execute(
                """
                SELECT ss.sub_specialty_name, ss.sub_specialty_requirements,
                       GROUP_CONCAT(sc.course_code, ', ') as courses
                FROM sub_specialties ss
                LEFT JOIN specialty_classes sc ON sc.sub_specialty_id = ss.id
                WHERE ss.specialty_id = ?
                GROUP BY ss.id
                ORDER BY ss.sub_specialty_name
                """,
                (row["id"],),
            )
            sub_specs = cur.fetchall()
            
            return {
                "name": row["specialty_name"],
                "type": row["specialty_type"],
                "notes": row["specialty_notes"],
                "program": row["program_name"],
                "sub_specialties": [
                    {
                        "name": ss["sub_specialty_name"],
                        "requirements": ss["sub_specialty_requirements"],
                        "courses": ss["courses"],
                    }
                    for ss in sub_specs
                ],
            }

    def compare_student_progress(
        self, 
        program_name: str, 
        completed_courses: List[str],
        current_courses: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Compare student's completed courses against program requirements.
        Based on query_degree_extra.py compare_courses_for_degree logic.
        
        Args:
            program_name: Program to check (e.g., 'MBA', 'MSIT')
            completed_courses: List of completed course codes (e.g., ['MIS 500', 'BUS 2080'])
            current_courses: Optional list of courses currently being taken
            
        Returns:
            Detailed analysis of program completion status including:
            - Overall completion status
            - Required vs Optional specialty progress
            - Per-specialty and per-sub-specialty completion details
            - Missing courses for each incomplete requirement
        """
        if not os.path.exists(self.db_path):
            return {"error": "Database not found"}
        
        current_courses = current_courses or []
        
        # Normalize course codes (uppercase, handle space variations)
        completed_set = {c.upper().replace(' ', '') for c in completed_courses}
        current_set = {c.upper().replace(' ', '') for c in current_courses}
        all_student_courses = completed_set | current_set
        
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # Try a multi-word name as-is first (e.g. "MBA in Analytics"); single
            # abbreviations ("MBA", "MSBA") go straight to the keyword mapping.
            # When a pattern matches several programs, the shortest name is the
            # closest match ("Master of Business Administration" over
            # "MBA in Analytics : Master of Business Administration").
            name = program_name.strip()
            keywords = ([name] if len(name.split()) > 1 else []) + self._extract_program_keywords(name)

            programs = []
            for keyword in keywords:
                pattern = f"%{keyword}%"
                cur.execute(
                    """
                    SELECT id, program_name, program_requirements
                    FROM programs
                    WHERE program_name LIKE ?
                    ORDER BY LENGTH(program_name)
                    LIMIT 1
                    """,
                    (pattern,),
                )
                result = cur.fetchone()
                if result:
                    programs.append(result)
                    break
            
            if not programs:
                return {"error": f"Program '{program_name}' not found in database"}
            
            program = programs[0]
            program_id = program["id"]
            program_full_name = program["program_name"]
            
            # Parse optional specialties requirement (e.g., "1" means 1 optional specialty needed)
            optional_required = 0
            req_str = program["program_requirements"]
            if req_str:
                try:
                    optional_required = int(req_str.strip())
                except ValueError:
                    # Try to extract number from text like "Complete 1 optional specialty"
                    match = re.search(r'(\d+)', str(req_str))
                    if match:
                        optional_required = int(match.group(1))
            
            # Get all specialties for this program
            cur.execute(
                """
                SELECT id, specialty_name, specialty_type
                FROM specialties
                WHERE program_id = ?
                """,
                (program_id,),
            )
            specialty_rows = cur.fetchall()
            
            analysis = {
                "program_name": program_full_name,
                "completed_courses": list(completed_courses),
                "current_courses": list(current_courses),
                "optional_specialties_needed": optional_required,
                "total_required_specialties": 0,
                "satisfied_required_specialties": 0,
                "total_optional_specialties": 0,
                "satisfied_optional_specialties": 0,
                "specialty_analysis": {},
                "overall_status": ""
            }
            
            for specialty_row in specialty_rows:
                spec_id = specialty_row["id"]
                spec_name = specialty_row["specialty_name"]
                spec_type = specialty_row["specialty_type"]
                
                # Get sub-specialties for this specialty
                cur.execute(
                    """
                    SELECT id, sub_specialty_name, sub_specialty_requirements
                    FROM sub_specialties
                    WHERE specialty_id = ?
                    """,
                    (spec_id,),
                )
                sub_spec_rows = cur.fetchall()
                
                sub_spec_analysis = {}
                total_satisfied_sub_specs = 0
                total_sub_specs = len(sub_spec_rows)
                
                for sub_spec_row in sub_spec_rows:
                    sub_spec_id = sub_spec_row["id"]
                    sub_spec_name = sub_spec_row["sub_specialty_name"]
                    sub_spec_req_str = sub_spec_row["sub_specialty_requirements"]
                    
                    # Get courses for this sub-specialty
                    cur.execute(
                        """
                        SELECT sc.course_code, c.Course_Title
                        FROM specialty_classes sc
                        LEFT JOIN courses c ON c.course_code = sc.course_code
                        WHERE sc.sub_specialty_id = ?
                        """,
                        (sub_spec_id,),
                    )
                    course_rows = cur.fetchall()
                    
                    all_courses = []
                    completed_in_sub = []
                    missing_in_sub = []
                    
                    for course_row in course_rows:
                        code = course_row["course_code"]
                        title = course_row["Course_Title"] or ""
                        normalized_code = code.upper().replace(' ', '') if code else ""
                        
                        course_info = {"code": code, "title": title}
                        all_courses.append(course_info)
                        
                        if normalized_code in all_student_courses:
                            completed_in_sub.append(course_info)
                        else:
                            missing_in_sub.append(course_info)
                    
                    # Determine requirement count
                    required_count = len(all_courses)  # Default: all courses required
                    if sub_spec_req_str:
                        try:
                            required_count = int(sub_spec_req_str.strip())
                        except ValueError:
                            match = re.search(r'(\d+)', str(sub_spec_req_str))
                            if match:
                                required_count = int(match.group(1))
                    
                    # Check if sub-specialty is satisfied
                    completed_count = len(completed_in_sub)
                    sub_spec_satisfied = completed_count >= required_count
                    
                    # Determine choice type
                    total_available = len(all_courses)
                    if required_count == total_available and required_count > 0:
                        choice_type = "All courses required"
                    elif required_count < total_available:
                        choice_type = f"Choose {required_count} of {total_available}"
                    else:
                        choice_type = "Requirements unclear"
                    
                    sub_spec_analysis[sub_spec_name] = {
                        "requirements": required_count,
                        "total_courses": total_available,
                        "completed_count": completed_count,
                        "completed_courses": completed_in_sub,
                        "missing_courses": missing_in_sub,
                        "satisfied": sub_spec_satisfied,
                        "choice_type": choice_type,
                        "status": "[OK] Satisfied" if sub_spec_satisfied else "[X] Incomplete"
                    }
                    
                    if sub_spec_satisfied:
                        total_satisfied_sub_specs += 1
                
                # Specialty is satisfied only if ALL sub-specialties are satisfied
                specialty_satisfied = (total_satisfied_sub_specs == total_sub_specs) and total_sub_specs > 0
                
                analysis["specialty_analysis"][spec_name] = {
                    "type": spec_type,
                    "sub_specialties": sub_spec_analysis,
                    "total_sub_specialties": total_sub_specs,
                    "satisfied_sub_specialties": total_satisfied_sub_specs,
                    "satisfied": specialty_satisfied,
                    "status": "[OK] Complete" if specialty_satisfied else "[X] Incomplete"
                }
                
                # Track required vs optional specialty completion
                if spec_type == "Required":
                    analysis["total_required_specialties"] += 1
                    if specialty_satisfied:
                        analysis["satisfied_required_specialties"] += 1
                elif spec_type == "Optional":
                    analysis["total_optional_specialties"] += 1
                    if specialty_satisfied:
                        analysis["satisfied_optional_specialties"] += 1
            
            # Determine overall program completion
            all_required_complete = (
                analysis["satisfied_required_specialties"] == analysis["total_required_specialties"]
            )
            enough_optional_complete = (
                analysis["satisfied_optional_specialties"] >= analysis["optional_specialties_needed"]
            )
            
            if all_required_complete and enough_optional_complete:
                analysis["overall_status"] = "COMPLETE - Program requirements satisfied!"
            elif analysis["satisfied_required_specialties"] > 0 or analysis["satisfied_optional_specialties"] > 0:
                analysis["overall_status"] = "IN PROGRESS - Some requirements satisfied"
            else:
                analysis["overall_status"] = "NOT STARTED - No specialties completed"
            
            return analysis
    
    def format_progress_report(self, analysis: Dict[str, Any]) -> str:
        """Format the progress analysis as readable text for the agent."""
        if "error" in analysis:
            return f"Error: {analysis['error']}"
        
        lines = []
        lines.append("PROGRAM COMPLETION ANALYSIS")
        lines.append("=" * 60)
        lines.append(f"Program: {analysis['program_name']}")
        
        if analysis['completed_courses']:
            lines.append(f"Completed Courses: {', '.join(analysis['completed_courses'])}")
        if analysis['current_courses']:
            lines.append(f"Currently Taking: {', '.join(analysis['current_courses'])}")
        lines.append("")
        
        # Calculate total courses from specialty analysis
        total_required_courses = 0
        total_optional_courses_completed = 0
        for spec_name, spec_data in analysis["specialty_analysis"].items():
            if spec_data["type"] == "Required":
                for sub_name, sub_data in spec_data["sub_specialties"].items():
                    total_required_courses += sub_data["requirements"]
            elif spec_data["type"] == "Optional" and spec_data["satisfied"]:
                for sub_name, sub_data in spec_data["sub_specialties"].items():
                    total_optional_courses_completed += sub_data["completed_count"]
        
        # Graduation requirements
        lines.append("GRADUATION REQUIREMENTS:")
        lines.append(f"   Required Specialties: {analysis['satisfied_required_specialties']}/{analysis['total_required_specialties']} complete ({total_required_courses} courses total)")
        lines.append(f"   Optional Specialties: {analysis['satisfied_optional_specialties']}/{analysis['total_optional_specialties']} complete (need {analysis['optional_specialties_needed']})")
        lines.append("")
        lines.append(f"Overall Status: {analysis['overall_status']}")
        lines.append("")
        
        # Specialty breakdown
        for spec_type in ["Required", "Optional"]:
            type_marker = "[REQ]" if spec_type == "Required" else "[OPT]"
            
            specialties_of_type = {
                name: data for name, data in analysis["specialty_analysis"].items()
                if data["type"] == spec_type
            }
            
            if not specialties_of_type:
                continue
            
            lines.append(f"{type_marker} {spec_type.upper()} SPECIALTIES:")
            lines.append("-" * 60)
            
            for spec_name, spec_analysis in specialties_of_type.items():
                # Calculate total courses for this specialty
                spec_total_courses = sum(sub["requirements"] for sub in spec_analysis["sub_specialties"].values())
                spec_completed_courses = sum(sub["completed_count"] for sub in spec_analysis["sub_specialties"].values())
                lines.append(f"\n{spec_analysis['status']} {spec_name} ({spec_completed_courses}/{spec_total_courses} courses)")
                lines.append(f"   Sub-Specialties: {spec_analysis['satisfied_sub_specialties']}/{spec_analysis['total_sub_specialties']} complete")
                
                for sub_spec_name, sub_spec_data in spec_analysis["sub_specialties"].items():
                    lines.append(f"   {sub_spec_data['status']} {sub_spec_name}")
                    lines.append(f"      Requirement: {sub_spec_data['choice_type']}")
                    lines.append(f"      Completed: {sub_spec_data['completed_count']}/{sub_spec_data['requirements']} courses")
                    
                    if sub_spec_data["completed_courses"]:
                        completed_list = ", ".join([c["code"] for c in sub_spec_data["completed_courses"]])
                        lines.append(f"      [DONE] Completed: {completed_list}")
                    
                    if not sub_spec_data["satisfied"] and sub_spec_data["missing_courses"]:
                        remaining = sub_spec_data["requirements"] - sub_spec_data["completed_count"]
                        if remaining > 0:
                            lines.append(f"      [TODO] Need {remaining} more from:")
                            for course in sub_spec_data["missing_courses"][:5]:  # Limit to 5
                                lines.append(f"         • {course['code']} - {course['title']}")
                            if len(sub_spec_data["missing_courses"]) > 5:
                                lines.append(f"         ... and {len(sub_spec_data['missing_courses']) - 5} more options")
                lines.append("")
            
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
