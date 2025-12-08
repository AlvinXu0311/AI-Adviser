"""
API endpoint for generating chat summaries using Gemini.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter()


class MessageItem(BaseModel):
    role: str
    content: str
    timestamp: str = ""


class SummaryRequest(BaseModel):
    messages: List[MessageItem]
    user_name: str = "User"
    include_recommendations: bool = True


class StudentInfo(BaseModel):
    program: str = ""
    courses_completed: List[str] = []
    courses_in_progress: List[str] = []
    gpa: str = ""
    specialties: List[str] = []


class SummaryResponse(BaseModel):
    success: bool
    summary: str
    student_info: StudentInfo = StudentInfo()
    key_topics: List[str] = []
    requirements_discussed: List[str] = []
    recommendations: List[str] = []
    error: str = ""


def get_gemini_model():
    """Get Gemini model for summary generation"""
    try:
        import google.generativeai as genai
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not configured")
        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        return genai.GenerativeModel(model_name)
    except Exception as e:
        logger.error(f"Failed to initialize Gemini model: {e}")
        raise


@router.post("/summarize", response_model=SummaryResponse)
async def generate_chat_summary(request: SummaryRequest):
    """
    Generate a detailed summary of the chat conversation using Gemini.
    
    Returns:
        - summary: Detailed narrative summary of the conversation
        - key_topics: List of main topics discussed
        - recommendations: List of actionable next steps
    """
    try:
        if not request.messages or len(request.messages) == 0:
            return SummaryResponse(
                success=False,
                summary="",
                key_topics=[],
                recommendations=[],
                error="No messages to summarize"
            )
        
        # Build conversation text for the prompt
        conversation_text = []
        for msg in request.messages:
            role_label = "Student" if msg.role == "user" else "Adviser"
            conversation_text.append(f"{role_label}: {msg.content}")
        
        conversation_str = "\n\n".join(conversation_text)
        
        # Build the summary prompt - concise and data-focused
        prompt = f"""You are an academic advisor at WPI Business School. Create a CONCISE summary of this advising session.

## Conversation:
{conversation_str}

## Instructions:
Extract and summarize KEY INFORMATION ONLY. Be brief and data-focused.

---SUMMARY---
Write a SHORT summary (2-3 sentences max) of what was discussed.

---STUDENT_INFO---
Extract specific student data mentioned (if any):
- Program/Degree: [e.g., MSIT, MBA, or "Not mentioned"]
- Courses Completed: [list specific courses mentioned, or "Not mentioned"]
- Courses In Progress: [list if mentioned]
- GPA: [if mentioned]
- Specialties/Concentrations: [if discussed]

---KEY_TOPICS---
List 3-5 main topics discussed (one line each):
- Topic 1
- Topic 2

---REQUIREMENTS_DISCUSSED---
List any specific program requirements or graduation requirements mentioned:
- [Requirement 1]
- [Requirement 2]

---RECOMMENDATIONS---
{"List 2-3 specific, actionable next steps:" if request.include_recommendations else "Skip this section"}
- Action 1
- Action 2

IMPORTANT: Be CONCISE. Only include information that was actually discussed. Do not add filler text or repeat information.
"""

        # Call Gemini API
        model = get_gemini_model()
        
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,  # Lower temperature for more focused output
                "max_output_tokens": 1500,  # Reduced to encourage conciseness
            }
        )
        
        response_text = response.text if hasattr(response, 'text') else str(response)
        
        # Parse the response
        summary = ""
        student_info = StudentInfo()
        key_topics = []
        requirements_discussed = []
        recommendations = []
        
        def parse_bullet_list(text: str) -> List[str]:
            """Parse bullet points from text"""
            items = []
            for line in text.strip().split("\n"):
                line = line.strip()
                if line.startswith("-") or line.startswith("•"):
                    item = line[1:].strip()
                    if item and item not in ["Not mentioned", "[Not mentioned]"]:
                        items.append(item)
                elif line.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                    item = line[2:].strip()
                    if item and item not in ["Not mentioned", "[Not mentioned]"]:
                        items.append(item)
            return items
        
        def get_section(text: str, start_marker: str, end_markers: List[str]) -> str:
            """Extract section between markers"""
            if start_marker not in text:
                return ""
            parts = text.split(start_marker)
            if len(parts) < 2:
                return ""
            section = parts[1]
            for end_marker in end_markers:
                if end_marker in section:
                    section = section.split(end_marker)[0]
                    break
            return section.strip()
        
        # Parse SUMMARY
        summary = get_section(
            response_text, 
            "---SUMMARY---", 
            ["---STUDENT_INFO---", "---KEY_TOPICS---", "---REQUIREMENTS_DISCUSSED---", "---RECOMMENDATIONS---"]
        )
        
        # Parse STUDENT_INFO
        student_info_text = get_section(
            response_text,
            "---STUDENT_INFO---",
            ["---KEY_TOPICS---", "---REQUIREMENTS_DISCUSSED---", "---RECOMMENDATIONS---"]
        )
        if student_info_text:
            for line in student_info_text.split("\n"):
                line = line.strip()
                if line.startswith("- Program") or line.startswith("Program"):
                    value = line.split(":", 1)[-1].strip() if ":" in line else ""
                    if value and value.lower() not in ["not mentioned", "[not mentioned]"]:
                        student_info.program = value
                elif "Courses Completed" in line:
                    value = line.split(":", 1)[-1].strip() if ":" in line else ""
                    if value and value.lower() not in ["not mentioned", "[not mentioned]"]:
                        # Parse comma-separated courses
                        courses = [c.strip() for c in value.split(",") if c.strip() and c.strip().lower() not in ["not mentioned"]]
                        student_info.courses_completed = courses
                elif "Courses In Progress" in line or "Current Courses" in line:
                    value = line.split(":", 1)[-1].strip() if ":" in line else ""
                    if value and value.lower() not in ["not mentioned", "[not mentioned]"]:
                        courses = [c.strip() for c in value.split(",") if c.strip() and c.strip().lower() not in ["not mentioned"]]
                        student_info.courses_in_progress = courses
                elif "GPA" in line:
                    value = line.split(":", 1)[-1].strip() if ":" in line else ""
                    if value and value.lower() not in ["not mentioned", "[not mentioned]"]:
                        student_info.gpa = value
                elif "Specialt" in line or "Concentration" in line:
                    value = line.split(":", 1)[-1].strip() if ":" in line else ""
                    if value and value.lower() not in ["not mentioned", "[not mentioned]"]:
                        specialties = [s.strip() for s in value.split(",") if s.strip() and s.strip().lower() not in ["not mentioned"]]
                        student_info.specialties = specialties
        
        # Parse KEY_TOPICS
        key_topics_text = get_section(
            response_text,
            "---KEY_TOPICS---",
            ["---REQUIREMENTS_DISCUSSED---", "---RECOMMENDATIONS---", "---STUDENT_INFO---"]
        )
        key_topics = parse_bullet_list(key_topics_text)
        
        # Parse REQUIREMENTS_DISCUSSED
        requirements_text = get_section(
            response_text,
            "---REQUIREMENTS_DISCUSSED---",
            ["---RECOMMENDATIONS---", "---KEY_TOPICS---"]
        )
        requirements_discussed = parse_bullet_list(requirements_text)
        
        # Parse RECOMMENDATIONS
        recommendations_text = get_section(
            response_text,
            "---RECOMMENDATIONS---",
            ["---SUMMARY---", "---KEY_TOPICS---", "---STUDENT_INFO---"]  # These shouldn't appear after
        )
        recommendations = parse_bullet_list(recommendations_text)
        
        # Fallback if parsing failed
        if not summary:
            summary = response_text[:500] if len(response_text) > 500 else response_text
        
        logger.info(f"Generated summary for {len(request.messages)} messages")
        
        return SummaryResponse(
            success=True,
            summary=summary,
            student_info=student_info,
            key_topics=key_topics[:5],  # Limit to 5 topics
            requirements_discussed=requirements_discussed[:5],  # Limit to 5 requirements
            recommendations=recommendations[:3],  # Limit to 3 recommendations
            error=""
        )
        
    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        return SummaryResponse(
            success=False,
            summary="",
            student_info=StudentInfo(),
            key_topics=[],
            requirements_discussed=[],
            recommendations=[],
            error=str(e)
        )
