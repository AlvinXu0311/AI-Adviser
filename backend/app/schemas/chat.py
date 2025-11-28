from pydantic import BaseModel, Field
from typing import Optional, List


class IntentClassification(BaseModel):
    """
    Free-form intent classification result from LLM.
    No enum constraints - LLM decides intent description freely.
    """
    intent: str = Field(
        ...,
        description="Free-form description of user's intent (e.g., 'asking about personal transcript info', 'course requirements query')"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence that query is meaningful and answerable (0-1)"
    )
    is_academic: bool = Field(
        default=True,
        description="Whether query relates to academic advising (programs, courses, transcript, planning)"
    )
    requires_transcript: bool = Field(
        default=False,
        description="Whether answering this query requires student's uploaded transcript data"
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of the classification decision"
    )


class TranscriptContext(BaseModel):
    """Schema for student transcript context in chat"""
    student_name: Optional[str] = Field(None, description="Student's full name")
    gpa: Optional[float] = Field(None, ge=0.0, le=4.0, description="GPA (0.0-4.0)")
    program: Optional[str] = Field(None, description="Program name")
    course_count: Optional[int] = Field(None, ge=0, description="Total number of courses taken")


class ChatRequest(BaseModel):
    """Schema for chat request"""
    message: str = Field(..., min_length=1, max_length=5000, description="Chat message from user")
    transcript_context: Optional[TranscriptContext] = Field(
        None,
        description="Optional student transcript context for personalized responses"
    )
    session_id: Optional[str] = Field(
        None,
        description="Optional session ID for conversation memory - generates one if not provided"
    )
    topic_id: Optional[str] = Field(
        None,
        description="Selected advising topic: 'general' (General Advising) or 'course' (Courses & Planning)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "message": "What courses should I take next?",
                "session_id": "abc123def456",
                "transcript_context": {
                    "student_name": "John Doe",
                    "gpa": 3.85,
                    "program": "MS in Business Analytics",
                    "course_count": 12
                }
            }
        }


class ChatResponse(BaseModel):
    """Schema for chat response"""
    response: str = Field(..., description="Response from LLM assistant")
    intent: Optional[IntentClassification] = Field(
        None,
        description="Intent classification of the user's question (optional)"
    )
    response_source: str = Field(
        default="llm",
        description="Source of response: 'llm' or 'agentic_rag'"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "response": "Based on your transcript and GPA, I recommend taking...",
                "intent": {
                    "intent": "personal transcript query - asking about their own academic info",
                    "confidence": 0.92,
                    "is_academic": True,
                    "requires_transcript": True,
                    "reasoning": "User is asking about their own data from uploaded transcript"
                },
                "response_source": "agentic_rag"
            }
        }
