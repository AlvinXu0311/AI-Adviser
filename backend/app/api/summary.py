"""
API endpoint for generating chat summaries using Gemini.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import logging
import os

from ..config import gemini_model

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
        model_name = gemini_model()
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
        
        # Build conversation text for the prompt - filter out system/empty messages
        conversation_text = []
        user_questions = []  # Track user questions for fallback
        
        for msg in request.messages:
            content = msg.content.strip()
            # Skip empty or very short messages
            if not content or len(content) < 5:
                continue
            # Skip file upload notifications and system messages
            if any(skip in content for skip in [
                "Uploaded Document:", "Transcript_", ".pdf", ".PDF",
                "**Uploaded", "File uploaded", "Document uploaded"
            ]):
                continue
            
            role_label = "Student" if msg.role == "user" else "Adviser"
            
            # Track user questions for fallback summary
            if msg.role == "user":
                # Clean up the question
                clean_q = content.replace("**", "").strip()
                if len(clean_q) > 10:
                    user_questions.append(clean_q[:100])
            
            # Truncate very long messages to key parts (keep more context)
            if len(content) > 800:
                content = content[:800] + "..."
            conversation_text.append(f"{role_label}: {content}")
        
        if not conversation_text:
            return SummaryResponse(
                success=True,
                summary="This was a brief advising session with minimal discussion.",
                student_info=StudentInfo(),
                key_topics=[],
                requirements_discussed=[],
                recommendations=["Schedule a follow-up session for detailed advising"],
                error=""
            )
        
        # Limit conversation length to avoid Gemini token limits
        conversation_str = "\n\n".join(conversation_text)
        if len(conversation_str) > 6000:
            # Take first and last parts to capture context
            conversation_str = conversation_str[:3000] + "\n\n[... middle of conversation omitted ...]\n\n" + conversation_str[-2500:]
            logger.info(f"Truncated conversation from {len(conversation_str)} chars for summary")
        
        # Build the summary prompt - focused on narrative summary
        prompt = f"""You are an academic advisor at WPI Business School. Write a professional summary of this advising session.

## Conversation:
{conversation_str}

## Task:
Write a clear, informative summary in 2-3 SHORT paragraphs (total 150-200 words max):

**Paragraph 1 - Topics Discussed:** What did the student ask about? List the main topics/programs/courses discussed.

**Paragraph 2 - Key Information:** What specific advice was given? Include course codes, credit requirements, program names when mentioned.

**Paragraph 3 - Next Steps (optional):** Brief recommendations if applicable.

## Requirements:
- Professional tone, complete sentences
- Be specific with course codes and program names
- Do NOT use bullet points
- Keep it CONCISE (150-200 words total)

## Example:
"During this advising session, the student inquired about the MBA program requirements and specialization options. The session focused on understanding the core curriculum and selecting appropriate electives.

The MBA program requires 30 credits total, including 7 core courses (BUS 590, FIN 500, MIS 584, MKT 500, OBC 506, OIE 501, and BUS 599 Capstone) and 3 specialty concentrations. The student expressed interest in Business Analytics and Data Science tracks, which include courses like MIS 502 and OIE 552.

As next steps, the student should review the specialization requirements and meet with their faculty advisor to finalize their course schedule for the upcoming semester."

Now write the summary:"""

        # Call Gemini API
        model = get_gemini_model()
        
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,  # Lower temperature for more focused output
                "max_output_tokens": 1500,  # Reduced to encourage conciseness
            }
        )
        
        # Handle cases where response might be blocked or empty
        response_text = ""
        try:
            if hasattr(response, 'text') and response.text:
                response_text = response.text
            elif hasattr(response, 'parts') and response.parts:
                response_text = "".join(part.text for part in response.parts if hasattr(part, 'text'))
            elif hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and candidate.content:
                        for part in candidate.content.parts:
                            if hasattr(part, 'text'):
                                response_text += part.text
        except Exception as text_error:
            logger.warning(f"Could not extract text from response: {text_error}")
            # Check if response was blocked
            if hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'finish_reason'):
                        logger.warning(f"Response finish reason: {candidate.finish_reason}")
                    if hasattr(candidate, 'safety_ratings'):
                        logger.warning(f"Safety ratings: {candidate.safety_ratings}")
        
        if not response_text:
            logger.warning("Empty response from Gemini, generating fallback summary")
            # Generate a meaningful fallback summary using collected user questions
            # user_questions was populated during message filtering above
            
            if user_questions:
                # Create a proper narrative summary from the questions
                questions_summary = ""
                if len(user_questions) == 1:
                    questions_summary = user_questions[0]
                elif len(user_questions) == 2:
                    questions_summary = f"{user_questions[0]} and {user_questions[1]}"
                else:
                    questions_summary = ", ".join(user_questions[:-1]) + f", and {user_questions[-1]}"
                
                adviser_count = len([m for m in request.messages if m.role == "assistant"])
                
                fallback_summary = (
                    f"During this advising session, the student inquired about the following topics: {questions_summary}. "
                    f"The academic adviser provided {adviser_count} response(s) with relevant information and guidance. "
                    f"For complete details on the topics discussed, please refer to the full conversation transcript above."
                )
            else:
                fallback_summary = (
                    "This advising session covered various academic topics. "
                    "Please review the conversation transcript above for specific details on the information discussed."
                )
            
            return SummaryResponse(
                success=True,
                summary=fallback_summary,
                student_info=StudentInfo(),
                key_topics=[],
                requirements_discussed=[],
                recommendations=[],
                error=""
            )
        
        # Clean up the response - remove any markdown formatting artifacts
        summary = response_text.strip()
        
        # Remove common unwanted prefixes
        unwanted_prefixes = ["Here is the summary:", "Summary:", "**Summary:**", "Here's the summary:"]
        for prefix in unwanted_prefixes:
            if summary.lower().startswith(prefix.lower()):
                summary = summary[len(prefix):].strip()
        
        # Ensure summary is a reasonable length (not too long)
        if len(summary) > 1500:
            # Find a good breaking point
            sentences = summary.split(". ")
            truncated = []
            current_len = 0
            for sentence in sentences:
                if current_len + len(sentence) < 1200:
                    truncated.append(sentence)
                    current_len += len(sentence) + 2
                else:
                    break
            summary = ". ".join(truncated)
            if not summary.endswith("."):
                summary += "."
        
        logger.info(f"Generated summary for {len(request.messages)} messages ({len(summary)} chars)")
        
        return SummaryResponse(
            success=True,
            summary=summary,
            student_info=StudentInfo(),  # Simplified - info is in the narrative summary
            key_topics=[],  # Simplified - topics are in the narrative
            requirements_discussed=[],  # Simplified
            recommendations=[],  # Simplified
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
