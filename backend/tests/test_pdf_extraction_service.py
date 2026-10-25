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
        # The structuring step is a Gemini call; give it the JSON the model returns, fenced in
        # markdown with a trailing comma, to exercise the cleanup and field mapping
        service.llm_backend = Mock()
        service.llm_backend.generate_content.return_value = Mock(text="""```json
{"student_name": "John Doe", "student_id": "A00123456", "gpa": 3.85,
 "program_info": {"program_name": "MS in Business Analytics", "enrollment_date": "2023-09-01"},
 "completed_courses": [{"course_code": "BUS501", "course_name": "Introduction to Business Analytics",
                        "credits": 3, "grade": "A"},],
 "current_courses": []}
```""")

        result = await service.process_pdf(mock_pdf_base64)

        assert isinstance(result, ExtractedTranscriptData)
        assert result.student_name == "John Doe"
        assert result.gpa == 3.85
        assert result.program_info.program_name == "MS in Business Analytics"
        assert [(c.course_code, c.grade) for c in result.completed_courses] == [("BUS501", "A")]
        # The model only ever sees the extracted text, sent with a deadline and retry policy
        prompt, = service.llm_backend.generate_content.call_args.args
        assert "BUS501" in prompt
        assert "request_options" in service.llm_backend.generate_content.call_args.kwargs

    @pytest.mark.asyncio
    async def test_process_pdf_extraction_failure(self, service, mock_pdf_base64):
        """Test error handling when text extraction fails"""
        service.extract_text_from_pdf = AsyncMock(side_effect=ValueError("Extraction failed"))

        with pytest.raises(ValueError, match="PDF processing failed"):
            await service.process_pdf(mock_pdf_base64)
