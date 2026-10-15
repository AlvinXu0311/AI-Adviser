"""
API endpoints for transcript extraction and processing.
"""
from fastapi import APIRouter, HTTPException
from ..schemas.transcript import (
    ExtractTranscriptRequest,
    ExtractTranscriptResponse,
    ExtractedTranscriptData,
)
from ..services.pdf_extraction_service import PDFExtractionService
from ..services.context_manager import get_context_manager

router = APIRouter()

# Lazy initialization - service created on first request, not at module load
# This ensures .env is fully loaded before service initializes
_pdf_service = None


def get_pdf_service():
    """Get or create PDFExtractionService (lazy initialization)"""
    global _pdf_service
    if _pdf_service is None:
        _pdf_service = PDFExtractionService()
    return _pdf_service


@router.post("/extract-transcript", response_model=ExtractTranscriptResponse)
async def extract_transcript(request: ExtractTranscriptRequest) -> ExtractTranscriptResponse:
    """
    Extract and parse transcript data from a base64 encoded PDF.
    Also stores the extracted data in context_manager for subsequent chat requests.

    Args:
        request: ExtractTranscriptRequest containing base64 PDF and session_id

    Returns:
        ExtractTranscriptResponse with extracted data or error message
    """
    try:
        # Validate request
        if not request.pdf_base64 or len(request.pdf_base64) == 0:
            raise ValueError("PDF data is required")
        
        if not request.session_id or len(request.session_id) == 0:
            raise ValueError("Session ID is required")

        # Process PDF
        transcript_data: ExtractedTranscriptData = await get_pdf_service().process_pdf(
            request.pdf_base64
        )

        # Store in context manager for subsequent chat requests (session-based)
        context_manager = get_context_manager()
        
        # Convert Pydantic model to dict for storage
        transcript_dict = {
            "student_name": transcript_data.student_name,
            "student_id": transcript_data.student_id,
            "gpa": transcript_data.gpa,
            "degree_program": transcript_data.program_info.program_name if transcript_data.program_info else None,
            "courses": [
                {
                    "course_code": c.course_code,
                    "course_name": c.course_name,
                    "credits": c.credits,
                    "grade": c.grade,
                    "semester": c.semester
                }
                for c in (transcript_data.completed_courses or [])
            ],
            "current_courses": [
                {
                    "course_code": c.course_code,
                    "course_name": c.course_name,
                    "credits": c.credits,
                    "semester": c.semester
                }
                for c in (transcript_data.current_courses or [])
            ],
            "transcript_text": transcript_data.raw_text
        }
        context_manager.set_student_context(request.session_id, transcript_dict)

        return ExtractTranscriptResponse(
            success=True,
            data=transcript_data,
            error=None,
        )

    except ValueError as e:
        return ExtractTranscriptResponse(
            success=False,
            data=None,
            error=str(e),
        )
    except Exception as e:
        return ExtractTranscriptResponse(
            success=False,
            data=None,
            error=f"Unexpected error: {str(e)}",
        )
