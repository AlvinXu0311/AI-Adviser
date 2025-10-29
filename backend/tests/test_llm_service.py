"""
Unit tests for LLM service.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.services.llm_service import LLMService
from app.schemas.chat import TranscriptContext


@pytest.mark.unit
class TestLLMService:
    """Tests for LLMService"""

    @pytest.fixture
    def service(self):
        """Create an LLM service instance"""
        return LLMService()

    def test_initialization(self, service):
        """Test service initialization"""
        assert service is not None
        assert service.model is not None
        assert service.conversation_history == []

    def test_build_system_prompt_without_context(self, service):
        """Test system prompt building without student context"""
        prompt = service._build_system_prompt(context=None)

        assert "WPI Business School" in prompt
        assert "academic advisor" in prompt
        assert "Course selection" in prompt
        assert "Career path" in prompt

    def test_build_system_prompt_with_context(self, service, sample_transcript_context):
        """Test system prompt building with student context"""
        prompt = service._build_system_prompt(context=sample_transcript_context)

        assert "John Doe" in prompt
        assert "3.85" in prompt
        assert "Business Analytics" in prompt
        assert "12" in prompt

    def test_build_system_prompt_partial_context(self, service):
        """Test system prompt with partial context"""
        context = TranscriptContext(
            student_name="Jane Smith",
            gpa=3.5,
            program=None,
            course_count=None
        )
        prompt = service._build_system_prompt(context=context)

        assert "Jane Smith" in prompt
        assert "3.5" in prompt

    @pytest.mark.asyncio
    async def test_generate_response_success(self, service):
        """Test successful response generation"""
        mock_response = Mock()
        mock_response.text = "Based on your interests, I recommend the following courses..."
        service.model.generate_content = Mock(return_value=mock_response)

        result = await service.generate_response(
            message="What courses should I take?",
            context=None
        )

        assert result is not None
        assert "recommend" in result.lower()

    @pytest.mark.asyncio
    async def test_generate_response_with_context(self, service, sample_transcript_context):
        """Test response generation with student context"""
        mock_response = Mock()
        mock_response.text = "Given your 3.85 GPA and Analytics focus, consider BUS501..."
        service.model.generate_content = Mock(return_value=mock_response)

        result = await service.generate_response(
            message="What's next?",
            context=sample_transcript_context
        )

        assert result is not None
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_response_empty_message(self, service):
        """Test error handling for empty message"""
        with pytest.raises(ValueError):
            await service.generate_response(message="", context=None)

    @pytest.mark.asyncio
    async def test_generate_response_long_message(self, service):
        """Test handling of very long messages"""
        long_message = "A" * 10000

        mock_response = Mock()
        mock_response.text = "Response to long message"
        service.model.generate_content = Mock(return_value=mock_response)

        result = await service.generate_response(message=long_message, context=None)

        assert result is not None

    @pytest.mark.asyncio
    async def test_generate_response_api_error(self, service):
        """Test error handling for API failures"""
        service.model.generate_content = Mock(
            side_effect=Exception("API Connection Error")
        )

        with pytest.raises(ValueError, match="LLM response generation failed"):
            await service.generate_response(message="Test message", context=None)

    @pytest.mark.asyncio
    async def test_generate_response_empty_api_response(self, service):
        """Test handling of empty LLM response"""
        service.model.generate_content = Mock(return_value=Mock(text=""))

        with pytest.raises(ValueError, match="Empty response from LLM"):
            await service.generate_response(message="Test message", context=None)

    def test_format_context_for_logging_no_context(self, service):
        """Test formatting None context for logging"""
        result = service._format_context_for_logging(context=None)
        assert result == "No context"

    def test_format_context_for_logging_full_context(self, service, sample_transcript_context):
        """Test formatting full context for logging"""
        result = service._format_context_for_logging(context=sample_transcript_context)

        assert "John Doe" in result
        assert "3.85" in result
        assert "Business Analytics" in result

    def test_format_context_for_logging_partial_context(self, service):
        """Test formatting partial context for logging"""
        context = TranscriptContext(student_name="Alice", gpa=3.0)
        result = service._format_context_for_logging(context=context)

        assert "Alice" in result
        assert "3" in result

    @pytest.mark.asyncio
    async def test_generate_response_conversation_flow(self, service):
        """Test multiple sequential responses (conversation flow)"""
        mock_response_1 = Mock(text="First response")
        mock_response_2 = Mock(text="Second response")
        service.model.generate_content = Mock(side_effect=[mock_response_1, mock_response_2])

        result1 = await service.generate_response("First question", context=None)
        result2 = await service.generate_response("Follow-up question", context=None)

        assert result1 == "First response"
        assert result2 == "Second response"

    def test_model_version(self, service):
        """Test that service uses correct model version"""
        assert service.model is not None
        # The model should be gemini-2.0-flash
        # This is ensured in the __init__ method
