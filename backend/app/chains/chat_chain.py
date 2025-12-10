"""
Chat Chain using LangChain with context awareness and CoT reasoning.
Integrates with RAG chain for knowledge-grounded responses.
"""
from typing import Optional, Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, SystemMessage
import logging
import os

from ..schemas.chat import TranscriptContext

logger = logging.getLogger(__name__)


class ChatChain:
    """
    Chat chain with context awareness and Chain of Thought reasoning.
    Provides conversational interface with student context.
    """

    def __init__(self):
        """Initialize chat chain with language model"""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")

        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.7,
            max_output_tokens=2048,
            google_api_key=api_key
        )

        self.thinking_enabled = True
        self.conversation_history = []

    def _build_system_prompt(self, context: Optional[TranscriptContext] = None) -> str:
        """Build system prompt with student context"""
        base_prompt = """You are an academic adviser for WPI Business School.

Your Role:
- Answer student questions about programs, courses, and academic progress
- Help plan course schedules based on student background
- Provide guidance on specializations and career paths
- Answer questions about student transcripts

Important Instructions:
- ONLY use information provided in context or retrieved from knowledge base
- Do NOT make up course names or program details
- Be direct and concise in responses
- Answer the specific question asked
- Do NOT provide unsolicited advice
- When discussing grades, only comment if explicitly asked
- Admit when you don't have information: "I don't have that information"

Response Style:
- Concise and professional
- Reference specific courses/programs when relevant
- Use student's transcript context when applicable"""

        if not context:
            return base_prompt

        # Add student context
        context_prompt = "\n\nStudent Information:\n"
        if context.student_name:
            context_prompt += f"- Name: {context.student_name}\n"
        if context.gpa is not None:
            context_prompt += f"- GPA: {context.gpa}/4.0\n"
        if context.program:
            context_prompt += f"- Program: {context.program}\n"
        if context.course_count is not None:
            context_prompt += f"- Completed Courses: {context.course_count}\n"

        return base_prompt + context_prompt

    async def generate_response(
        self,
        message: str,
        context: Optional[TranscriptContext] = None,
        rag_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a response using the chat chain.

        Args:
            message: User's message
            context: Optional student transcript context
            rag_context: Optional context from RAG retrieval

        Returns:
            Dict with response, reasoning, and metadata
        """
        try:
            logger.info(f"Chat chain processing: {message[:50]}...")

            # Build system prompt
            system_prompt = self._build_system_prompt(context)

            # Add RAG context if available
            if rag_context:
                system_prompt += f"\n\nProgram Knowledge Base:\n{rag_context}"
                logger.info(f"RAG context injected ({len(rag_context)} chars)")

            # Create messages
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=message)
            ]

            # Add conversation history if needed
            if self.conversation_history:
                messages = self.conversation_history + messages

            # Generate response
            logger.info("Invoking LLM with CoT reasoning...")
            response = self.llm.invoke(messages)

            response_text = response.content

            # Store in history
            self.conversation_history.append(HumanMessage(content=message))
            self.conversation_history.append(response)

            # Keep history manageable (last 20 messages for better context)
            if len(self.conversation_history) > 20:
                self.conversation_history = self.conversation_history[-20:]

            logger.info(f"Chat response generated: {len(response_text)} chars")

            return {
                "response": response_text,
                "reasoning": "LangChain chat with CoT pattern",
                "has_context": context is not None,
                "has_rag": rag_context is not None,
                "source": "chat_chain"
            }

        except Exception as e:
            logger.error(f"Error in chat chain: {str(e)}", exc_info=True)
            raise ValueError(f"Chat chain processing failed: {str(e)}")

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
        logger.info("Conversation history cleared")


# Singleton instance
_chat_chain = None


def get_chat_chain() -> ChatChain:
    """Get or create the chat chain"""
    global _chat_chain
    if _chat_chain is None:
        _chat_chain = ChatChain()
    return _chat_chain
