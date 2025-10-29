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

    def test_initialization(self, service):
        """Test service initialization"""
        assert service is not None
        assert service.model is not None

    @pytest.mark.asyncio
    @patch("app.services.pdf_extraction_service.genai.GenerativeModel")
    async def test_extract_text_from_pdf_success(self, mock_genai, service, mock_pdf_base64):
        """Test successful text extraction from PDF"""
        # Mock the Gemini response
        mock_response = Mock()
        mock_response.text = "Student Name: John Doe\nGPA: 3.85\nCourse: BUS501"
        service.model.generate_content = Mock(return_value=mock_response)

        # Call the method
        result = await service.extract_text_from_pdf(mock_pdf_base64)

        # Verify results
        assert result is not None
        assert "John Doe" in result
        assert "3.85" in result

    @pytest.mark.asyncio
    async def test_extract_text_from_pdf_empty_response(self, service, mock_pdf_base64):
        """Test error handling when API returns empty response"""
        service.model.generate_content = Mock(return_value=Mock(text=""))

        with pytest.raises(ValueError, match="Failed to extract text from PDF"):
            await service.extract_text_from_pdf(mock_pdf_base64)

    @pytest.mark.asyncio
    async def test_extract_text_from_pdf_api_error(self, service, mock_pdf_base64):
        """Test error handling for API failures"""
        service.model.generate_content = Mock(side_effect=Exception("API Error"))

        with pytest.raises(ValueError, match="PDF text extraction failed"):
            await service.extract_text_from_pdf(mock_pdf_base64)

    def test_parse_transcript_text_with_complete_data(self, service):
        """Test parsing transcript text with complete data"""
        transcript_text = """
        Student Name: John Doe
        Student ID: A00123456
        GPA: 3.85
        Program: MS in Business Analytics

        BUS501 - Introduction to Business Analytics - 3 - A
        BUS502 - Data Analysis Fundamentals - 3 - A-
        """

        result = service.parse_transcript_text(transcript_text)

        assert result.student_name == "John Doe"
        assert result.student_id == "A00123456"
        assert result.gpa == 3.85
        assert result.program_info.program_name == "MS in Business Analytics"
        assert len(result.completed_courses) >= 2

    def test_parse_transcript_text_partial_data(self, service):
        """Test parsing transcript text with partial data"""
        transcript_text = """
        Student Name: Jane Smith
        GPA: 3.5
        """

        result = service.parse_transcript_text(transcript_text)

        assert result.student_name == "Jane Smith"
        assert result.gpa == 3.5
        assert result.student_id is None

    def test_parse_transcript_text_no_gpa(self, service):
        """Test parsing transcript text without GPA"""
        transcript_text = """
        Student Name: Bob Johnson
        """

        result = service.parse_transcript_text(transcript_text)

        assert result.student_name == "Bob Johnson"
        assert result.gpa is None

    def test_parse_transcript_text_invalid_gpa(self, service):
        """Test parsing transcript text with invalid GPA value"""
        transcript_text = """
        Student Name: Alice Brown
        GPA: 5.0
        """

        result = service.parse_transcript_text(transcript_text)

        assert result.student_name == "Alice Brown"
        # GPA should be None because 5.0 is outside valid range
        assert result.gpa is None

    def test_parse_transcript_text_multiple_courses(self, service):
        """Test parsing multiple courses from transcript"""
        transcript_text = """
        BUS501 - Intro to Analytics - 3 - A
        BUS502 - Data Analysis - 3 - B+
        BUS503 - Advanced Analytics - 4 - A-
        """

        result = service.parse_transcript_text(transcript_text)

        assert result.completed_courses is not None
        assert len(result.completed_courses) == 3
        assert result.completed_courses[0].course_code == "BUS501"
        assert result.completed_courses[1].grade == "B+"
        assert result.completed_courses[2].credits == 4.0

    def test_parse_transcript_text_empty_input(self, service):
        """Test parsing empty transcript text"""
        result = service.parse_transcript_text("")

        assert result.student_name is None
        assert result.gpa is None
        assert result.completed_courses is None

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

    def test_parse_program_extraction(self, service):
        """Test extraction of program information"""
        transcript_text = """
        Program: MS in Business Analytics
        Enrolled: 09/01/2023
        """

        result = service.parse_transcript_text(transcript_text)

        assert result.program_info is not None
        assert "Business Analytics" in result.program_info.program_name

    def test_parse_different_course_formats(self, service):
        """Test parsing courses with different formats"""
        transcript_text = """
        BUS101 - Intro Course - 3 - A
        MGMT201 - Management - 4 - B+
        ECON301 - Economics - 3
        """

        result = service.parse_transcript_text(transcript_text)

        # Should extract at least 2 courses with grades
        assert result.completed_courses is not None
        assert len([c for c in result.completed_courses if c.grade]) >= 2
