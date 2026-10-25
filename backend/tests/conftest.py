"""
Pytest configuration and shared fixtures for backend tests.
"""
import os

# Auth and transcript storage need these before the app is imported
os.environ.setdefault("APP_JWT_SECRET", "test-secret-for-pytest-only-0123456789abcdef")
os.environ.setdefault("CONTEXT_STORE", "memory")

import pytest
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, patch

import fakeredis
from app.schemas.transcript import ExtractedTranscriptData, CourseInfo, ProgramInfo
from app.schemas.chat import TranscriptContext, ChatRequest, ChatResponse
from datetime import date


RUN_LIVE = os.getenv("RUN_LIVE_TESTS") == "1"
if RUN_LIVE:
    # Live tests use the real key from backend/.env
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


def pytest_collection_modifyitems(config, items):
    """Skip tests that call the real Gemini API unless explicitly requested (they cost money)."""
    if RUN_LIVE:
        return
    skip = pytest.mark.skip(reason="calls the real Gemini API; run with RUN_LIVE_TESTS=1")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


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


@pytest.fixture
def fake_redis():
    """Shared fake Redis for session ownership (same decode_responses as the real client)."""
    client = fakeredis.FakeRedis(decode_responses=True)
    memory = SimpleNamespace(redis_client=client)
    with patch("app.services.session_access.get_conversation_memory", return_value=memory), \
            patch("app.services.rate_limit.get_conversation_memory", return_value=memory), \
            patch("app.auth._redis", return_value=client):
        yield client


def auth_headers(email: str = "student@wpi.edu", name: str = "Student") -> dict:
    """Bearer header with a real backend-issued token."""
    from app.auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token(email, name)}"}


@pytest.fixture
def auth_client(fake_redis):
    """TestClient that sends a valid token on every request."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    client.headers.update(auth_headers())
    return client
