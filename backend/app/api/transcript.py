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
from ..utils.error_handler import handle_pdf_extraction_error

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
        request: ExtractTranscriptRequest containing base64 PDF

    Returns:
        ExtractTranscriptResponse with extracted data or error message
    """
    try:
        # Validate request
        if not request.pdf_base64 or len(request.pdf_base64) == 0:
            raise ValueError("PDF data is required")

        # Process PDF
        transcript_data: ExtractedTranscriptData = await get_pdf_service().process_pdf(
            request.pdf_base64
        )

        # Store in context manager for subsequent chat requests
        context_manager = get_context_manager()
        context_manager.set_student_context(transcript_data)

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
