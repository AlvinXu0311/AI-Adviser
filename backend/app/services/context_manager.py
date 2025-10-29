"""
Context Manager Service for managing shared cache/memory between PDF and Chat LLM services.
Stores student context, chat history, and provides efficient access to cached information.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import json
from ..schemas.transcript import ExtractedTranscriptData, CourseInfo, ProgramInfo


class ContextManager:
    """Manages shared context and cache for PDF and Chat LLM services"""

    def __init__(self, cache_ttl_minutes: int = 60):
        """
        Initialize context manager with optional TTL for cache.

        Args:
            cache_ttl_minutes: Time-to-live for cached data in minutes
        """
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self.student_context: Optional[ExtractedTranscriptData] = None
        self.context_timestamp: Optional[datetime] = None
        self.chat_history: List[Dict[str, Any]] = []
        print("[ContextManager] Initialized context manager")

    def set_student_context(self, context: ExtractedTranscriptData) -> None:
        """
        Store student context from PDF extraction.
        This context is shared with chat service.

        Args:
            context: Extracted transcript data
        """
        self.student_context = context
        self.context_timestamp = datetime.now()
        print(f"\n[ContextManager] Stored student context:")
        print(f"   - Student: {context.student_name}")
        print(f"   - ID: {context.student_id}")
        print(f"   - GPA: {context.gpa}")
        print(f"   - Program: {context.program_info.program_name if context.program_info else 'N/A'}")
        print(f"   - Completed Courses: {len(context.completed_courses) if context.completed_courses else 0}")
        if context.completed_courses:
            for c in context.completed_courses:
                print(f"       - {c.course_code}: {c.course_name} (Grade: {c.grade})")
        print(f"   - Current Courses: {len(context.current_courses) if context.current_courses else 0}")
        if context.current_courses:
            for c in context.current_courses:
                print(f"       - {c.course_code}: {c.course_name}")

    def get_student_context(self) -> Optional[ExtractedTranscriptData]:
        """
        Get cached student context.

        Returns:
            Cached student context or None if expired/not set
        """
        if self.student_context is None:
            return None

        # Check if cache is expired
        if self.context_timestamp and datetime.now() - self.context_timestamp > self.cache_ttl:
            print("[ContextManager] Student context cache expired")
            self.student_context = None
            return None

        print(f"[ContextManager] Retrieved cached student context")
        return self.student_context

    def add_chat_message(self, role: str, content: str) -> None:
        """
        Add message to chat history.

        Args:
            role: "user" or "assistant"
            content: Message content
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        self.chat_history.append(message)
        print(f"📝 [ContextManager] Added {role} message to history (total: {len(self.chat_history)})")

    def get_chat_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get chat history.

        Args:
            limit: Optional limit on number of messages to return

        Returns:
            List of chat messages
        """
        if limit:
            return self.chat_history[-limit:]
        return self.chat_history

    def clear_chat_history(self) -> None:
        """Clear chat history."""
        self.chat_history.clear()
        print(" [ContextManager] Cleared chat history")

    def get_context_summary(self) -> Dict[str, Any]:
        """
        Get summary of current context for use in prompts.

        Returns:
            Dictionary with student context summary
        """
        context = self.get_student_context()
        if not context:
            return {}

        summary = {
            "student_name": context.student_name,
            "student_id": context.student_id,
            "gpa": context.gpa,
            "program": context.program_info.program_name if context.program_info else None,
            "completed_courses_count": len(context.completed_courses) if context.completed_courses else 0,
            "current_courses_count": len(context.current_courses) if context.current_courses else 0,
            "completed_courses": [
                {
                    "code": c.course_code,
                    "name": c.course_name,
                    "credits": c.credits,
                    "grade": c.grade
                }
                for c in (context.completed_courses or [])
            ] if context.completed_courses else [],
            "current_courses": [
                {
                    "code": c.course_code,
                    "name": c.course_name,
                    "credits": c.credits
                }
                for c in (context.current_courses or [])
            ] if context.current_courses else []
        }

        print(f"[ContextManager] Generated context summary")
        return summary

    def get_context_for_prompt(self) -> str:
        """
        Get context as formatted string for including in LLM prompts.

        Returns:
            Formatted context string
        """
        summary = self.get_context_summary()
        if not summary:
            return "No student context available."

        courses_str = ""
        if summary.get("completed_courses"):
            courses_str = "\n**Completed Courses:**\n"
            for c in summary["completed_courses"]:
                courses_str += f"  - {c['code']}: {c['name']} ({c['credits']} credits, Grade: {c['grade']})\n"

        context_str = f"""
**Student Information:**
- Name: {summary.get('student_name', 'N/A')}
- Student ID: {summary.get('student_id', 'N/A')}
- GPA: {summary.get('gpa', 'N/A')}
- Program: {summary.get('program', 'N/A')}

**Academic Status:**
- Completed Courses: {summary.get('completed_courses_count', 0)}
- Current Courses: {summary.get('current_courses_count', 0)}
{courses_str}
"""
        return context_str

    def is_context_available(self) -> bool:
        """Check if student context is available and not expired."""
        return self.get_student_context() is not None

    def get_academic_progress(self) -> Dict[str, Any]:
        """
        Evaluate student's academic progress based on ACTUAL TRANSCRIPT DATA.
        Focuses on course quality, grades, and specific course requirements - not just credit counts.

        Returns:
            Dictionary with detailed progress evaluation based on transcript
        """
        context = self.get_student_context()
        if not context:
            return {}

        # Analyze completed courses - focus on quality and grades
        completed_courses_list = []
        failed_courses = []
        strong_courses = []  # A or A-

        if context.completed_courses:
            for course in context.completed_courses:
                course_info = {
                    "code": course.course_code,
                    "name": course.course_name,
                    "credits": course.credits or 0,
                    "grade": course.grade
                }
                completed_courses_list.append(course_info)

                # Categorize by performance
                if course.grade:
                    grade_upper = course.grade.upper()
                    if grade_upper.startswith('F') or grade_upper == 'D':
                        failed_courses.append(course_info)
                    elif grade_upper.startswith('A'):
                        strong_courses.append(course_info)

        # Analyze current courses - focus on course types and sequence
        current_courses_list = []
        current_credits = 0

        if context.current_courses:
            for course in context.current_courses:
                credits = course.credits or 0
                current_credits += credits
                current_courses_list.append({
                    "code": course.course_code,
                    "name": course.course_name,
                    "credits": credits
                })

        # Build comprehensive progress evaluation
        progress = {
            # Student info
            "student_name": context.student_name,
            "gpa": context.gpa,
            "program": context.program_info.program_name if context.program_info else None,

            # Completed courses - detailed breakdown
            "completed_courses": completed_courses_list,
            "completed_course_count": len(completed_courses_list),
            "strong_performance_courses": strong_courses,
            "failed_courses": failed_courses,

            # Current courses
            "current_courses": current_courses_list,
            "current_course_count": len(current_courses_list),
            "current_credits": current_credits,

            # Academic status evaluation
            "academic_performance": self._evaluate_academic_performance(context.gpa, failed_courses, strong_courses),
            "course_progression": self._evaluate_course_progression(completed_courses_list, current_courses_list),
            "academic_standing": self._evaluate_academic_standing(context.gpa, failed_courses),

            # Detailed summary
            "summary": self._generate_detailed_summary(context, completed_courses_list, current_courses_list, failed_courses)
        }

        print(f"\n[ContextManager] Academic Progress Evaluation:")
        print(f"   - Student: {progress['student_name']}")
        print(f"   - GPA: {progress['gpa']}")
        print(f"   - Program: {progress['program']}")
        print(f"   - Completed Courses: {progress['completed_course_count']}")
        print(f"   - Current Courses: {progress['current_course_count']}")
        print(f"   - Academic Performance: {progress['academic_performance']}")
        print(f"   - Academic Standing: {progress['academic_standing']}")
        print(f"   - Course Progression: {progress['course_progression']}")
        if failed_courses:
            print(f"   [WARNING] Failed/Low Courses: {len(failed_courses)}")

        return progress

    def _evaluate_academic_performance(self, gpa: Optional[float], failed_courses: list, strong_courses: list) -> str:
        """
        Evaluate overall academic performance based on GPA, grades, and course quality.

        Args:
            gpa: Student's GPA
            failed_courses: List of failed/D grade courses
            strong_courses: List of A/A- grade courses

        Returns:
            Performance assessment
        """
        if not gpa:
            return "Insufficient data"

        if failed_courses:
            return "Needs Improvement (has failed courses)"

        if gpa >= 3.7:
            return "Excellent (3.7+ GPA)"
        elif gpa >= 3.5:
            return "Very Good (3.5-3.7 GPA)"
        elif gpa >= 3.0:
            return "Good (3.0-3.5 GPA)"
        elif gpa >= 2.7:
            return "Satisfactory (2.7-3.0 GPA)"
        else:
            return "At Risk (below 2.7 GPA)"

    def _evaluate_academic_standing(self, gpa: Optional[float], failed_courses: list) -> str:
        """
        Evaluate academic standing based on GPA and failed courses.

        Args:
            gpa: Student's GPA
            failed_courses: List of failed courses

        Returns:
            Academic standing status
        """
        if failed_courses:
            return "Probation/Warning (has failed courses)"

        if not gpa:
            return "Unknown"

        if gpa >= 3.0:
            return "Good Standing"
        elif gpa >= 2.0:
            return "Satisfactory Standing"
        else:
            return "Academic Probation"

    def _evaluate_course_progression(self, completed_courses: list, current_courses: list) -> str:
        """
        Evaluate course progression and sequence based on completed and current courses.

        Args:
            completed_courses: List of completed courses
            current_courses: List of current courses

        Returns:
            Course progression assessment
        """
        if not completed_courses:
            return "Just Starting"

        if len(current_courses) == 0:
            return "Completed (No current courses)"

        if len(completed_courses) < 3:
            return "Early Stage"
        elif len(completed_courses) < 7:
            return "Mid-Program"
        else:
            return "Advanced"

    def _generate_detailed_summary(self, context, completed_courses: list, current_courses: list, failed_courses: list) -> str:
        """
        Generate a detailed academic summary based on actual course data.

        Args:
            context: Student context from transcript
            completed_courses: List of completed courses
            current_courses: List of current courses
            failed_courses: List of failed courses

        Returns:
            Detailed summary string
        """
        summary = f"Academic Summary for {context.student_name}:\n"

        # Program and GPA
        if context.program_info:
            summary += f"Program: {context.program_info.program_name}\n"
        if context.gpa:
            summary += f"GPA: {context.gpa}/4.0\n"

        # Course progress
        summary += f"\nCourse Progress:\n"
        summary += f"- Completed: {len(completed_courses)} courses\n"
        summary += f"- Currently Taking: {len(current_courses)} courses\n"

        # Specific course details
        if completed_courses:
            summary += f"\nCompleted Courses:\n"
            for course in completed_courses:
                summary += f"  • {course['code']}: {course['name']} (Grade: {course['grade']}, Credits: {course['credits']})\n"

        if current_courses:
            summary += f"\nCurrent Courses:\n"
            for course in current_courses:
                summary += f"  • {course['code']}: {course['name']} (Credits: {course['credits']})\n"

        # Warning about failed courses
        if failed_courses:
            summary += f"\n[WARNING] Failed Courses:\n"
            for course in failed_courses:
                summary += f"  • {course['code']}: {course['name']} (Grade: {course['grade']})\n"
            summary += f"\nRecommendation: Consider retaking failed courses or seeking academic support.\n"

        return summary


# Global context manager instance (shared across services)
_context_manager = None


def get_context_manager() -> ContextManager:
    """Get or create global context manager instance."""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
