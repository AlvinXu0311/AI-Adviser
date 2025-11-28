"""Helper functions that convert database payloads into user-facing text."""
from __future__ import annotations

from typing import List, Dict, Any, Optional
from ..schemas.chat import IntentType


def program_response(snapshot: Dict[str, Any], query: str) -> str:
    """Format a Business School database snapshot for program-oriented intents."""
    if not snapshot:
        return _no_results_message(query)

    if "error" in snapshot:
        return f"Business School database error: {snapshot['error']}"

    programs = snapshot.get("programs", [])
    if not programs:
        return _no_results_message(query)

    lines: List[str] = ["According to the Business School database:"]

    for program in programs:
        lines.append(
            f"\n{program.get('program', 'Program')} (Code: {program.get('code') or 'N/A'})"
        )
        lines.append(
            f"Level: {program.get('level') or 'N/A'} | Type: {program.get('type') or 'N/A'}"
        )
        if program.get("description"):
            lines.append(f"Overview: {program['description']}")
        required_specialties = program.get("optional_specialties_required")
        if required_specialties is not None:
            lines.append(
                f"Optional specialties required to graduate: {required_specialties}"
            )

        specialties = program.get("specialties", {})
        for spec_name, spec_payload in specialties.items():
            lines.append(f"  • Specialty: {spec_name}")
            if spec_payload.get("description"):
                lines.append(f"    Description: {spec_payload['description']}")
            if spec_payload.get("requirements") is not None:
                lines.append(
                    f"    Optional courses required: {spec_payload['requirements']}"
                )
            required_courses = _format_course_list(spec_payload.get("required", []))
            optional_courses = _format_course_list(spec_payload.get("optional", []))
            if required_courses:
                lines.append(f"    Required courses: {required_courses}")
            if optional_courses:
                lines.append(f"    Optional courses: {optional_courses}")

    return "\n".join(lines).strip()


def academic_progress_response(student_context) -> str:
    """Summarize the cached transcript information for the student."""
    if not student_context:
        return (
            "I do not have your transcript on file. Please upload your PDF so I can "
            "discuss GPA, completed courses, and degree progress."
        )

    lines = ["Here is the transcript information I have on file:"]
    if getattr(student_context, "student_name", None):
        lines.append(f"- Name: {student_context.student_name}")
    if getattr(student_context, "student_id", None):
        lines.append(f"- Student ID: {student_context.student_id}")
    if getattr(student_context, "gpa", None) is not None:
        lines.append(f"- GPA: {student_context.gpa}/4.0")
    if getattr(student_context, "program_info", None) and getattr(student_context.program_info, "program_name", None):
        lines.append(f"- Program: {student_context.program_info.program_name}")

    completed = len(getattr(student_context, "completed_courses", []) or [])
    current = len(getattr(student_context, "current_courses", []) or [])
    lines.append(f"- Completed courses on record: {completed}")
    lines.append(f"- Current courses on record: {current}")
    lines.append(
        "If any of this information is outdated, please upload an updated transcript."
    )
    return "\n".join(lines)


def clarify_response(intent: IntentType, query: str) -> str:
    """Fallback message when we cannot map a query to structured data."""
    if intent == IntentType.CAREER_ADVICE:
        return (
            "Career advising questions are outside the scope of the Business School "
            "database. Please reach out to a career mentor for tailored guidance."
        )
    if intent == IntentType.GENERAL_ACADEMIC:
        return (
            "I could not match your question to a specific program or course. "
            "Try including the program name or the course topic you want to explore."
        )
    return (
        "I was unable to fulfill that request with the Business School database. "
        "Please rephrase or provide more details."
    )


def _format_course_list(courses: Optional[List[Dict[str, Any]]]) -> str:
    if not courses:
        return ""
    display = []
    for course in courses[:5]:
        code = course.get("code") or course.get("subject") or "Course"
        title = course.get("title") or ""
        credits = course.get("credits")
        credit_suffix = f" ({credits} cr)" if credits is not None else ""
        if title:
            display.append(f"{code} {title}{credit_suffix}")
        else:
            display.append(f"{code}{credit_suffix}")
    remainder = max(0, len(courses) - 5)
    if remainder:
        display.append(f"...+{remainder} more")
    return ", ".join(display)


def _no_results_message(query: str) -> str:
    return (
        "The Business School database did not return a match for that description. "
        "Please double-check the program name or include more specific keywords."
    )
