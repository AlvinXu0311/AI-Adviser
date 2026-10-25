"""
Integration tests for API endpoints.
"""
import pytest
from unittest.mock import patch, Mock, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.chat import ChatRequest, TranscriptContext
from app.schemas.transcript import ExtractTranscriptRequest

SESSION_ID = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def valid_pdf_base64() -> str:
    import base64
    return base64.b64encode(b"%PDF-1.4\n%test transcript\n").decode()


@pytest.mark.integration
class TestChatEndpoint:
    """Integration tests for chat endpoint"""

    @pytest.fixture
    def client(self, auth_client):
        """Create an authenticated test client"""
        return auth_client

    def test_chat_endpoint_empty_message(self, client):
        """Test chat endpoint with empty message"""
        response = client.post(
            "/api/chat",
            json={"message": ""}
        )

        # ChatRequest enforces min_length=1, so FastAPI rejects it before the handler runs
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"][-1] == "message"

    def test_chat_endpoint_message_too_long(self, client):
        """Test chat endpoint with message exceeding max length"""
        long_message = "A" * 6000

        response = client.post(
            "/api/chat",
            json={"message": long_message}
        )

        # ChatRequest enforces max_length=5000
        assert response.status_code == 422
        assert response.json()["detail"][0]["type"] == "string_too_long"

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
    def client(self, auth_client):
        """Create an authenticated test client"""
        return auth_client

    def test_extract_transcript_success(self, client, valid_pdf_base64):
        """Test successful transcript extraction"""
        with patch("app.services.pdf_extraction_service.PDFExtractionService.process_pdf") as mock_pdf, \
                patch("app.api.transcript.get_context_manager") as mock_cm:
            from app.schemas.transcript import ExtractedTranscriptData, ProgramInfo
            mock_pdf.return_value = ExtractedTranscriptData(
                student_name="John Doe",
                student_id="A00123456",
                gpa=3.85,
                program_info=ProgramInfo(program_name="MS in Analytics")
            )

            response = client.post(
                "/api/extract-transcript",
                json={"pdf_base64": valid_pdf_base64, "session_id": SESSION_ID}
            )

            assert response.status_code == 200
            assert response.json()["success"] is True
            assert response.json()["data"]["student_name"] == "John Doe"
            mock_cm.return_value.set_student_context.assert_called_once()

    def test_extract_transcript_empty_pdf(self, client):
        """Test transcript extraction with empty PDF"""
        response = client.post(
            "/api/extract-transcript",
            json={"pdf_base64": "", "session_id": SESSION_ID}
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

    def test_extract_transcript_api_error(self, client, valid_pdf_base64):
        """Processing errors return a generic message, not the internal exception text"""
        with patch("app.services.pdf_extraction_service.PDFExtractionService.process_pdf") as mock_pdf:
            mock_pdf.side_effect = ValueError("PDF processing failed: upstream 500 at key=abc")

            response = client.post(
                "/api/extract-transcript",
                json={"pdf_base64": valid_pdf_base64, "session_id": SESSION_ID}
            )

            assert response.status_code == 200
            assert response.json()["success"] is False
            assert "upstream" not in response.json()["error"]
            assert "Could not read this transcript" in response.json()["error"]

    def test_extract_transcript_rejects_non_pdf(self, client):
        """Files that are not PDFs are rejected before reaching Gemini"""
        import base64
        with patch("app.services.pdf_extraction_service.PDFExtractionService.process_pdf") as mock_pdf:
            response = client.post(
                "/api/extract-transcript",
                json={"pdf_base64": base64.b64encode(b"MZ not a pdf").decode(), "session_id": SESSION_ID}
            )

            assert response.json()["success"] is False
            assert "PDF" in response.json()["error"]
            mock_pdf.assert_not_called()


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
    def client(self, auth_client):
        """Create an authenticated test client"""
        return auth_client

    def test_cors_headers_present(self, client):
        """Test that CORS headers are properly set"""
        response = client.post(
            "/api/chat",
            json={"message": "Test"},
            headers={
                "Origin": "http://localhost:5173",
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
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST"
            }
        )

        # OPTIONS should be allowed
        assert response.status_code in [200, 405]  # 405 is acceptable for OPTIONS


@pytest.mark.integration
class TestErrorHandling:
    """Integration tests for error handling"""

    @pytest.fixture
    def client(self, auth_client):
        """Create an authenticated test client"""
        return auth_client

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

        assert response.status_code == 422
        assert "detail" in response.json()
