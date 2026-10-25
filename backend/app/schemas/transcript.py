from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
import os

# Largest transcript PDF accepted, and the matching base64 length (4 chars per 3 bytes)
MAX_TRANSCRIPT_BYTES = int(os.getenv("MAX_TRANSCRIPT_MB", "10")) * 1024 * 1024
MAX_TRANSCRIPT_BASE64_CHARS = (MAX_TRANSCRIPT_BYTES + 2) // 3 * 4


class CourseInfo(BaseModel):
    """Schema for course information extracted from transcript"""
    course_code: str = Field(..., description="Course code (e.g., BUS501)")
    course_name: str = Field(..., description="Course name")
    credits: float = Field(..., ge=0, description="Number of credits")
    grade: Optional[str] = Field(None, description="Grade received (e.g., A, B+, etc)")
    semester: Optional[str] = Field(None, description="Semester taken (e.g., Fall 2023)")


class ProgramInfo(BaseModel):
    """Schema for program information extracted from transcript"""
    program_name: str = Field(..., description="Name of the program (e.g., MS in Business Analytics)")
    enrollment_date: Optional[date] = Field(None, description="Program enrollment date")
    expected_graduation_date: Optional[date] = Field(None, description="Expected graduation date")


class ExtractedTranscriptData(BaseModel):
    """Schema for complete extracted transcript data"""
    student_name: Optional[str] = Field(None, description="Student's full name")
    student_id: Optional[str] = Field(None, description="Student ID number")
    gpa: Optional[float] = Field(None, ge=0.0, le=4.0, description="GPA (0.0-4.0)")
    completed_courses: Optional[List[CourseInfo]] = Field(None, description="List of completed courses")
    current_courses: Optional[List[CourseInfo]] = Field(None, description="List of current courses")
    program_info: Optional[ProgramInfo] = Field(None, description="Program information")
    raw_text: Optional[str] = Field(None, description="Raw extracted text from PDF")

    class Config:
        json_schema_extra = {
            "example": {
                "student_name": "John Doe",
                "student_id": "A00123456",
                "gpa": 3.85,
                "completed_courses": [
                    {
                        "course_code": "BUS501",
                        "course_name": "Introduction to Business Analytics",
                        "credits": 3,
                        "grade": "A",
                        "semester": "Fall 2023"
                    }
                ],
                "current_courses": [
                    {
                        "course_code": "BUS502",
                        "course_name": "Advanced Analytics",
                        "credits": 3,
                        "grade": None,
                        "semester": "Spring 2024"
                    }
                ],
                "program_info": {
                    "program_name": "MS in Business Analytics",
                    "enrollment_date": "2023-09-01",
                    "expected_graduation_date": "2025-05-31"
                }
            }
        }


class ExtractTranscriptRequest(BaseModel):
    """Schema for transcript extraction request"""
    pdf_base64: str = Field(..., max_length=MAX_TRANSCRIPT_BASE64_CHARS, description="Base64 encoded PDF file content")
    session_id: str = Field(..., max_length=128, description="Unique session identifier from the frontend")

    class Config:
        json_schema_extra = {
            "example": {
                "pdf_base64": "JVBERi0xLjQKJeLj... (truncated for brevity)",
                "session_id": "abc123-def456-ghi789"
            }
        }


class ExtractTranscriptResponse(BaseModel):
    """Schema for transcript extraction response"""
    success: bool = Field(..., description="Whether extraction was successful")
    data: Optional[ExtractedTranscriptData] = Field(None, description="Extracted transcript data")
    error: Optional[str] = Field(None, description="Error message if extraction failed")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "data": {
                    "student_name": "John Doe",
                    "student_id": "A00123456",
                    "gpa": 3.85,
                    "completed_courses": [],
                    "current_courses": [],
                    "program_info": None
                },
                "error": None
            }
        }
