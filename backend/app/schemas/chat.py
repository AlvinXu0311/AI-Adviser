from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class IntentType(str, Enum):
    """Enum for different intent types"""
    COURSE_SELECTION = "course_selection"
    PROGRAM_REQUIREMENTS = "program_requirements"
    ACADEMIC_PROGRESS = "academic_progress"
    CAREER_ADVICE = "career_advice"
    PREREQUISITE = "prerequisite"
    GPA_RELATED = "gpa_related"
    SCHEDULE_PLANNING = "schedule_planning"
    GENERAL_ACADEMIC = "general_academic"
    OTHER = "other"


class IntentClassification(BaseModel):
    """Schema for intent classification result"""
    intent: IntentType = Field(..., description="Primary intent of the question")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    secondary_intents: List[IntentType] = Field(
        default_factory=list,
        description="Secondary intents if multiple are detected"
    )
    requires_transcript: bool = Field(
        default=False,
        description="Whether transcript context is needed for this query"
    )
    rule_applicable: bool = Field(
        default=False,
        description="Whether rule-based system can handle this query"
    )
    suggested_response_type: str = Field(
        default="llm",
        description="Suggested response type: 'llm', 'rule_based', or 'hybrid'"
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

    class Config:
        json_schema_extra = {
            "example": {
                "message": "What courses should I take next?",
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
        description="Source of response: 'llm', 'rule_based', or 'hybrid'"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "response": "Based on your transcript and GPA, I recommend taking...",
                "intent": {
                    "intent": "course_selection",
                    "confidence": 0.92,
                    "secondary_intents": [],
                    "requires_transcript": True,
                    "rule_applicable": True,
                    "suggested_response_type": "hybrid"
                },
                "response_source": "hybrid"
            }
        }
