"""
Error handling utilities for the API.
"""
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)


class PDFExtractionError(Exception):
    """Custom exception for PDF extraction errors"""
    pass


class LLMError(Exception):
    """Custom exception for LLM service errors"""
    pass


def handle_pdf_extraction_error(error: Exception) -> HTTPException:
    """
    Handle PDF extraction errors and return appropriate HTTP response.

    Args:
        error: The exception that occurred

    Returns:
        HTTPException with appropriate status code
    """
    logger.error(f"PDF extraction error: {str(error)}")

    if isinstance(error, ValueError):
        return HTTPException(status_code=400, detail=str(error))
    else:
        return HTTPException(status_code=500, detail="Internal server error during PDF processing")


def handle_llm_error(error: Exception) -> HTTPException:
    """
    Handle LLM service errors and return appropriate HTTP response.

    Args:
        error: The exception that occurred

    Returns:
        HTTPException with appropriate status code
    """
    error_str = str(error)
    logger.error(f"LLM error: {error_str}", exc_info=True)
    logger.error(f"Error type: {type(error).__name__}")

    error_message = error_str.lower()

    # Check for API key issues
    if "api_key" in error_message or "authentication" in error_message:
        logger.error("✗ API authentication error detected")
        return HTTPException(
            status_code=401,
            detail="API authentication failed - Check GOOGLE_API_KEY environment variable"
        )

    # Check for rate limiting
    if "rate" in error_message or "quota" in error_message:
        logger.error("✗ Rate limit error detected")
        return HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later."
        )

    # Check for network/connection issues
    if "connection" in error_message or "timeout" in error_message or "network" in error_message:
        logger.error("✗ Network/connection error detected")
        return HTTPException(
            status_code=503,
            detail="Service temporarily unavailable. Please try again later."
        )

    # Check for invalid input
    if "invalid" in error_message:
        logger.error("✗ Invalid input error detected")
        return HTTPException(status_code=400, detail=error_str)

    # Check for empty response
    if "empty" in error_message:
        logger.error("✗ Empty response error detected")
        return HTTPException(
            status_code=500,
            detail="AI service returned empty response. Please try again."
        )

    # Generic error with more detail
    logger.error(f"✗ Unhandled LLM error: {error_str}")
    return HTTPException(
        status_code=500,
        detail=f"Error generating response: {error_str[:100]}"
    )


def validate_api_key() -> bool:
    """
    Validate that API key is configured.

    Returns:
        True if API key is configured

    Raises:
        HTTPException: If API key is not configured
    """
    import os
    if not os.getenv("GOOGLE_API_KEY"):
        logger.error("GOOGLE_API_KEY not configured")
        raise HTTPException(
            status_code=500,
            detail="API key not configured. Please set GOOGLE_API_KEY environment variable."
        )
    return True
