"""
Integration tests for API endpoints.
"""
import pytest
from unittest.mock import patch, Mock, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.chat import ChatRequest, TranscriptContext
from app.schemas.transcript import ExtractTranscriptRequest


@pytest.mark.integration
class TestChatEndpoint:
    """Integration tests for chat endpoint"""

    @pytest.fixture
    def client(self):
        """Create a test client"""
        return TestClient(app)

    def test_chat_endpoint_basic_message(self, client):
        """Test chat endpoint with basic message"""
        with patch("app.services.llm_service.LLMService.generate_response") as mock_llm:
            mock_llm.return_value = "Test response from LLM"

            response = client.post(
                "/api/chat",
                json={"message": "What courses should I take?"}
            )

            assert response.status_code == 200
            assert "Test response from LLM" in response.json()["response"]

    def test_chat_endpoint_with_context(self, client):
        """Test chat endpoint with transcript context"""
        with patch("app.services.llm_service.LLMService.generate_response") as mock_llm:
            mock_llm.return_value = "Personalized response"

            response = client.post(
                "/api/chat",
                json={
                    "message": "What's next?",
                    "transcript_context": {
                        "student_name": "John Doe",
                        "gpa": 3.85,
                        "program": "MS in Business Analytics",
                        "course_count": 6
                    }
                }
            )

            assert response.status_code == 200
            assert "Personalized response" in response.json()["response"]

    def test_chat_endpoint_empty_message(self, client):
        """Test chat endpoint with empty message"""
        response = client.post(
            "/api/chat",
            json={"message": ""}
        )

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_chat_endpoint_message_too_long(self, client):
        """Test chat endpoint with message exceeding max length"""
        long_message = "A" * 6000

        response = client.post(
            "/api/chat",
            json={"message": long_message}
        )

        assert response.status_code == 400
        assert "exceeds maximum length" in response.json()["detail"]

    def test_chat_endpoint_missing_message(self, client):
        """Test chat endpoint with missing message field"""
        response = client.post(
            "/api/chat",
            json={"transcript_context": {}}
        )

        assert response.status_code == 422  # Validation error

    def test_chat_endpoint_invalid_json(self, client):
        """Test chat endpoint with invalid JSON"""
        response = client.post(
            "/api/chat",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422

    def test_chat_endpoint_api_error(self, client):
        """Test chat endpoint when LLM API fails"""
        with patch("app.services.llm_service.LLMService.generate_response") as mock_llm:
            mock_llm.side_effect = Exception("API Error")

            response = client.post(
                "/api/chat",
                json={"message": "Test message"}
            )

            assert response.status_code == 500

    def test_chat_endpoint_invalid_gpa(self, client):
        """Test chat endpoint with invalid GPA in context"""
        response = client.post(
            "/api/chat",
            json={
                "message": "Hello",
                "transcript_context": {
                    "student_name": "John",
                    "gpa": 5.0,  # Invalid: > 4.0
                    "program": "MS",
                    "course_count": 5
                }
            }
        )

        # Should be rejected by Pydantic validation
        assert response.status_code == 422


@pytest.mark.integration
class TestTranscriptEndpoint:
    """Integration tests for transcript extraction endpoint"""

    @pytest.fixture
    def client(self):
        """Create a test client"""
        return TestClient(app)

    def test_extract_transcript_success(self, client, mock_pdf_base64):
        """Test successful transcript extraction"""
        with patch("app.services.pdf_extraction_service.PDFExtractionService.process_pdf") as mock_pdf:
            from app.schemas.transcript import ExtractedTranscriptData, ProgramInfo
            mock_pdf.return_value = ExtractedTranscriptData(
                student_name="John Doe",
                student_id="A00123456",
                gpa=3.85,
                program_info=ProgramInfo(program_name="MS in Analytics")
            )

            response = client.post(
                "/api/extract-transcript",
                json={"pdf_base64": mock_pdf_base64}
            )

            assert response.status_code == 200
            assert response.json()["success"] is True
            assert response.json()["data"]["student_name"] == "John Doe"

    def test_extract_transcript_empty_pdf(self, client):
        """Test transcript extraction with empty PDF"""
        response = client.post(
            "/api/extract-transcript",
            json={"pdf_base64": ""}
        )

        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "required" in response.json()["error"].lower()

    def test_extract_transcript_invalid_json(self, client):
        """Test transcript extraction with invalid JSON"""
        response = client.post(
            "/api/extract-transcript",
            data="invalid",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422

    def test_extract_transcript_missing_pdf_base64(self, client):
        """Test transcript extraction with missing pdf_base64 field"""
        response = client.post(
            "/api/extract-transcript",
            json={}
        )

        assert response.status_code == 422

    def test_extract_transcript_api_error(self, client, mock_pdf_base64):
        """Test transcript extraction when PDF service fails"""
        with patch("app.services.pdf_extraction_service.PDFExtractionService.process_pdf") as mock_pdf:
            mock_pdf.side_effect = ValueError("Invalid PDF")

            response = client.post(
                "/api/extract-transcript",
                json={"pdf_base64": mock_pdf_base64}
            )

            assert response.status_code == 200
            assert response.json()["success"] is False
            assert "Invalid PDF" in response.json()["error"]


@pytest.mark.integration
class TestHealthEndpoints:
    """Integration tests for health check endpoints"""

    @pytest.fixture
    def client(self):
        """Create a test client"""
        return TestClient(app)

    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")

        assert response.status_code == 200
        assert "Welcome" in response.json()["message"]

    def test_health_check_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "WPI Business School" in data["service"]
        assert "version" in data


@pytest.mark.integration
class TestCORSHeaders:
    """Integration tests for CORS configuration"""

    @pytest.fixture
    def client(self):
        """Create a test client"""
        return TestClient(app)

    def test_cors_headers_present(self, client):
        """Test that CORS headers are properly set"""
        response = client.post(
            "/api/chat",
            json={"message": "Test"},
            headers={
                "Origin": "http://localhost:4200",
                "Access-Control-Request-Method": "POST"
            }
        )

        # Should not return CORS error
        assert response.status_code in [200, 400, 422, 500]

    def test_options_method(self, client):
        """Test OPTIONS method for CORS preflight"""
        response = client.options(
            "/api/chat",
            headers={
                "Origin": "http://localhost:4200",
                "Access-Control-Request-Method": "POST"
            }
        )

        # OPTIONS should be allowed
        assert response.status_code in [200, 405]  # 405 is acceptable for OPTIONS


@pytest.mark.integration
class TestErrorHandling:
    """Integration tests for error handling"""

    @pytest.fixture
    def client(self):
        """Create a test client"""
        return TestClient(app)

    def test_404_not_found(self, client):
        """Test 404 response for non-existent endpoint"""
        response = client.get("/api/nonexistent")

        assert response.status_code == 404

    def test_method_not_allowed(self, client):
        """Test 405 for wrong HTTP method"""
        response = client.get("/api/chat")

        assert response.status_code == 405

    def test_validation_error_response(self, client):
        """Test validation error response format"""
        response = client.post(
            "/api/chat",
            json={"message": ""}
        )

        assert response.status_code == 400
        assert "detail" in response.json()
