"""
Pytest configuration and shared fixtures for backend tests.
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from app.schemas.transcript import ExtractedTranscriptData, CourseInfo, ProgramInfo
from app.schemas.chat import TranscriptContext, ChatRequest, ChatResponse
from datetime import date


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_transcript_data() -> ExtractedTranscriptData:
    """Sample transcript data for testing."""
    return ExtractedTranscriptData(
        student_name="John Doe",
        student_id="A00123456",
        gpa=3.85,
        completed_courses=[
            CourseInfo(
                course_code="BUS501",
                course_name="Introduction to Business Analytics",
                credits=3,
                grade="A",
                semester="Fall 2023"
            ),
            CourseInfo(
                course_code="BUS502",
                course_name="Data Analysis Fundamentals",
                credits=3,
                grade="A-",
                semester="Spring 2024"
            ),
        ],
        current_courses=[
            CourseInfo(
                course_code="BUS503",
                course_name="Advanced Analytics",
                credits=3,
                grade=None,
                semester="Fall 2024"
            ),
        ],
        program_info=ProgramInfo(
            program_name="MS in Business Analytics",
            enrollment_date=date(2023, 9, 1),
            expected_graduation_date=date(2025, 5, 31)
        ),
        raw_text="Sample transcript text..."
    )


@pytest.fixture
def sample_transcript_context() -> TranscriptContext:
    """Sample transcript context for testing."""
    return TranscriptContext(
        student_name="John Doe",
        gpa=3.85,
        program="MS in Business Analytics",
        course_count=12
    )


@pytest.fixture
def sample_chat_request() -> ChatRequest:
    """Sample chat request for testing."""
    return ChatRequest(
        message="What courses should I take next?",
        transcript_context=TranscriptContext(
            student_name="John Doe",
            gpa=3.85,
            program="MS in Business Analytics",
            course_count=6
        )
    )


@pytest.fixture
def mock_gemini_model():
    """Mock Gemini model for testing."""
    mock = Mock()
    mock.generate_content = Mock(return_value=Mock(text="Mocked response from Gemini"))
    return mock


@pytest.fixture
def mock_pdf_base64() -> str:
    """Sample base64 encoded PDF for testing."""
    return "JVBERi0xLjQKJeLj78" + "X" * 100  # Simplified base64 sample


@pytest.fixture
@patch("google.generativeai.GenerativeModel")
def mock_genai_setup(mock_model):
    """Setup mocked Google Generative AI."""
    mock_instance = Mock()
    mock_instance.generate_content = AsyncMock(return_value=Mock(text="Test response"))
    mock_model.return_value = mock_instance
    return mock_model, mock_instance
