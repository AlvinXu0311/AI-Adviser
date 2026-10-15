"""
Unit tests for PDF extraction service.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.services.pdf_extraction_service import PDFExtractionService
from app.schemas.transcript import ExtractedTranscriptData, CourseInfo


@pytest.mark.unit
class TestPDFExtractionService:
    """Tests for PDFExtractionService"""

    @pytest.fixture
    def service(self):
        """Create a PDF extraction service instance"""
        return PDFExtractionService()

    @pytest.mark.asyncio
    @patch("app.services.pdf_extraction_service.PDFExtractionService.extract_text_from_pdf")
    async def test_process_pdf_success(self, mock_extract, service, mock_pdf_base64, sample_transcript_data):
        """Test successful PDF processing"""
        transcript_text = """
        Student Name: John Doe
        Student ID: A00123456
        GPA: 3.85
        Program: MS in Business Analytics

        BUS501 - Introduction to Business Analytics - 3 - A
        """
        mock_extract.return_value = transcript_text

        result = await service.process_pdf(mock_pdf_base64)

        assert isinstance(result, ExtractedTranscriptData)
        assert result.student_name == "John Doe"
        assert result.gpa == 3.85

    @pytest.mark.asyncio
    async def test_process_pdf_extraction_failure(self, service, mock_pdf_base64):
        """Test error handling when text extraction fails"""
        service.extract_text_from_pdf = AsyncMock(side_effect=ValueError("Extraction failed"))

        with pytest.raises(ValueError, match="PDF processing failed"):
            await service.process_pdf(mock_pdf_base64)
