"""
API endpoints for transcript extraction and processing.
"""
import asyncio
import base64
import binascii
import logging

from fastapi import APIRouter, Depends
from ..auth import User
from ..schemas.transcript import (
    ExtractTranscriptRequest,
    ExtractTranscriptResponse,
    ExtractedTranscriptData,
)
from ..services.pdf_extraction_service import PDFExtractionService
from ..services.context_manager import get_context_manager
from ..services.rate_limit import rate_limited
from ..services.session_access import claim_session
from ..services.untrusted import sanitize_transcript

logger = logging.getLogger(__name__)

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


def _validate_pdf(pdf_base64: str) -> None:
    """Reject anything that is not well-formed base64 of a PDF before it is sent to Gemini."""
    try:
        pdf_bytes = base64.b64decode(pdf_base64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Transcript must be a base64-encoded PDF file")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("Transcript must be a PDF file")


@router.post("/extract-transcript", response_model=ExtractTranscriptResponse)
async def extract_transcript(
    request: ExtractTranscriptRequest,
    user: User = Depends(rate_limited("transcript", "TRANSCRIPT_RATE_LIMIT_PER_HOUR", 10, 3600)),
) -> ExtractTranscriptResponse:
    """
    Extract and parse transcript data from a base64 encoded PDF.
    Also stores the extracted data in context_manager for subsequent chat requests.

    Args:
        request: ExtractTranscriptRequest containing base64 PDF and session_id

    Returns:
        ExtractTranscriptResponse with extracted data or error message
    """
    # Ownership check first: a session that belongs to someone else is a 403, not an error payload
    await asyncio.to_thread(claim_session, request.session_id, user)

    try:
        # Validate request
        if not request.pdf_base64 or len(request.pdf_base64) == 0:
            raise ValueError("PDF data is required")
        _validate_pdf(request.pdf_base64)
    except ValueError as e:
        return ExtractTranscriptResponse(success=False, data=None, error=str(e))

    try:
        # Process PDF
        transcript_data: ExtractedTranscriptData = await get_pdf_service().process_pdf(
            request.pdf_base64
        )

        # Store in context manager for subsequent chat requests (session-based)
        context_manager = get_context_manager()
        
        # Convert Pydantic model to dict for storage. The PDF is user-supplied, so only validated
        # fields are kept (prompt-injection defense, see services/untrusted.py)
        transcript_dict = sanitize_transcript({
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
        })
        await asyncio.to_thread(context_manager.set_student_context, request.session_id, transcript_dict)

        return ExtractTranscriptResponse(
            success=True,
            data=transcript_data,
            error=None,
        )

    except ValueError as e:
        # Processing errors can quote model output or SDK internals, so the client gets a generic message
        logger.warning("Transcript extraction failed: %s", e)
        return ExtractTranscriptResponse(
            success=False,
            data=None,
            error="Could not read this transcript. Please check that it is a text-based PDF and try again.",
        )
    except Exception:
        logger.exception("Unexpected error during transcript extraction")
        return ExtractTranscriptResponse(
            success=False,
            data=None,
            error="Unexpected error while reading the transcript. Please try again.",
        )
