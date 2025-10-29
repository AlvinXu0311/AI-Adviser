"""
LLM Service for generating context-aware responses.
Supports multiple providers: Google Gemini API or Local Llama3.1 model.
Integrates with RAG service for program-related questions.
"""
import os
from typing import Optional
from ..schemas.chat import TranscriptContext
from .context_manager import get_context_manager
from .rag_service import get_rag_service


class LLMService:
    """Service for LLM interactions with context-awareness and provider support"""

    def __init__(self):
        """Initialize the LLM service with configured provider"""
        self.provider = os.getenv("LLM_PROVIDER", "google").lower()
        self.conversation_history = []

        # Chain of Thought configuration
        self.thinking_enabled = os.getenv("THINKING_ENABLED", "true").lower() == "true"
        self.thinking_budget_default = int(os.getenv("THINKING_BUDGET_DEFAULT", "5000"))
        self.thinking_budget_complex = int(os.getenv("THINKING_BUDGET_COMPLEX", "10000"))
        self.thinking_budget_simple = int(os.getenv("THINKING_BUDGET_SIMPLE", "1000"))

        if self.provider == "llama":
            from .llama_service import get_llama_service
            self.llm_backend = get_llama_service()
            print(f"[LLM] Using Llama provider")
        elif self.provider == "google":
            # Use new API with native thinking support
            from google import genai
            from google.genai import types

            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY environment variable is required")

            self.genai_client = genai.Client(api_key=api_key)
            self.genai_types = types
            thinking_status = "enabled" if self.thinking_enabled else "disabled"
            print(f"[LLM] Using Google Gemini with NEW API (CoT: {thinking_status})")
        else:
            raise ValueError(f"Unknown LLM_PROVIDER: {self.provider}. Use 'google' or 'llama'")

    def _build_system_prompt(self, context: Optional[TranscriptContext] = None) -> str:
        """
        Build a system prompt with student context for personalized responses.

        Args:
            context: Optional student transcript context

        Returns:
            System prompt for the LLM
        """
        base_prompt = """You are an academic advisor for WPI Business School.

🎯 CRITICAL INSTRUCTION - ANSWER ONLY WHAT IS ASKED:
Do NOT add unsolicited commentary, suggestions, or advice.
Do NOT discuss grades unless asked about specific grades.
Do NOT provide tips or strategies unless explicitly requested.
Do NOT add "notes" or "observations" about performance.
Do NOT provide general advice alongside the answer.

RESPONSE STYLE:
- Answer the EXACT question asked
- Keep response brief and direct
- Only use transcript data if relevant to their question
- Do not add padding, extra information, or well-meaning advice
- If they ask "What's my progress?" → Answer progress, courses they have taken
- If they ask "What are my grades?" → List grades, nothing else
- If they ask "What courses did I take?" → List courses, nothing else

REASONING APPROACH (when program information is provided):
- Think through which parts of the provided information are most relevant
- Consider how different pieces of information relate to the student's question
- Verify your answer against the provided program data before responding
- If information seems contradictory, reason through which is most accurate

EXAMPLE:
WRONG: "Your progress is 12 credits completed out of 33 needed. I notice you have a C in MKT 565, so you might want to focus on stronger performance going forward."
RIGHT: "You have completed 12 credits out of 33 needed for the program."

Be helpful but minimal. Answer the question and stop.
"""

        if not context:
            return base_prompt

        # Add context-aware information
        context_prompt = f"\n\nStudent Information:\n"
        if context.student_name:
            context_prompt += f"- Name: {context.student_name}\n"
        if context.gpa is not None:
            context_prompt += f"- GPA: {context.gpa}/4.0\n"
        if context.program:
            context_prompt += f"- Program: {context.program}\n"
        if context.course_count is not None:
            context_prompt += f"- Courses Completed: {context.course_count}\n"

        # Add detailed academic evaluation from transcript
        context_manager = get_context_manager()
        progress = context_manager.get_academic_progress()
        if progress:
            context_prompt += f"\nAcademic Progress Evaluation:\n"
            context_prompt += f"- Academic Performance: {progress.get('academic_performance', 'Unknown')}\n"
            context_prompt += f"- Academic Standing: {progress.get('academic_standing', 'Unknown')}\n"
            context_prompt += f"- Course Progression: {progress.get('course_progression', 'Unknown')}\n"
            context_prompt += f"- Completed Courses: {progress.get('completed_course_count', 0)}\n"
            context_prompt += f"- Current Courses: {progress.get('current_course_count', 0)}\n"
            context_prompt += f"- Current Credits (In Progress): {progress.get('current_credits', 0)}\n"

            # Include detailed course information with grades
            if progress.get('completed_courses'):
                context_prompt += f"\nCompleted Courses (with Grades):\n"
                for course in progress['completed_courses']:
                    context_prompt += f"  - {course['code']}: {course['name']} | Grade: {course['grade']} | {course['credits']} credits\n"

            if progress.get('current_courses'):
                context_prompt += f"\nCurrent Courses (In Progress):\n"
                for course in progress['current_courses']:
                    context_prompt += f"  - {course['code']}: {course['name']} | {course['credits']} credits\n"

            # Highlight failed courses if any
            if progress.get('failed_courses'):
                context_prompt += f"\n[WARNING] Failed/Low Courses:\n"
                for course in progress['failed_courses']:
                    context_prompt += f"  - {course['code']}: {course['name']} | Grade: {course['grade']}\n"

        context_prompt += """

RESPONSE GUIDELINES:
- When they ask "How am I doing?" - just answer their question about progress
- When they ask "What courses did I take?" - just list the courses
- When they ask "What's my GPA?" - just state the GPA
- Do NOT add unsolicited analysis, recommendations, or suggestions
- Do NOT comment on grades unless specifically asked
- Use the course data only if directly relevant to their question
"""

        return base_prompt + context_prompt

    def _is_vague_question(self, message: str) -> bool:
        """
        Detect if a question is too vague and needs clarification.

        Args:
            message: User's message

        Returns:
            True if question is vague, False if specific enough
        """
        message_lower = message.lower().strip()

        # Vague patterns that need clarification
        vague_patterns = [
            "help",  # just "help"
            "tell me about",  # generic request
            "what can you do",  # asking about capabilities
            "what do you do",
            "how can you help",
            "can you help",  # alone without context
            "hi",
            "hello",
            "hey",
            "what",  # single word "what"
            "why",  # single word "why"
            "how",  # single word "how"
            "info",  # just "info"
            "information",  # just "information"
        ]

        # Check if message is too short or matches vague patterns
        if len(message_lower) < 5:
            return True

        for pattern in vague_patterns:
            if message_lower == pattern or message_lower.startswith(pattern + " ") and len(message_lower.split()) <= 3:
                return True

        return False

    def _assess_query_complexity(self, message: str) -> str:
        """
        Assess the complexity of a user query to determine appropriate thinking budget.

        Args:
            message: User's message

        Returns:
            Complexity level: "simple", "medium", or "complex"
        """
        message_lower = message.lower()

        # Complex query indicators
        complex_indicators = [
            "explain why", "why does", "why is", "why are",
            "how does", "how would", "how should", "how can",
            "compare", "difference between", "versus", "vs",
            "analyze", "evaluate", "assess",
            "what if", "suppose", "hypothetical",
            "pros and cons", "advantages and disadvantages",
            "best way to", "optimal", "recommend",
            "step by step", "walkthrough", "guide me",
            "multiple", "several", "both",
        ]

        # Medium complexity indicators
        medium_indicators = [
            "what are", "tell me about", "describe",
            "requirements for", "how many", "which",
            "list", "show me", "can i", "should i",
        ]

        # Simple query indicators (factual lookups)
        simple_indicators = [
            "what is my", "my gpa", "my progress", "my grade",
            "when is", "what time", "is there",
            "yes or no", "true or false",
        ]

        # Check for multi-part questions (AND/OR logic)
        has_multiple_parts = any(conn in message_lower for conn in [" and ", " or ", ", and", ", or"])
        question_marks = message.count("?")

        # Count words as additional complexity factor
        word_count = len(message.split())

        # Assess complexity
        if any(indicator in message_lower for indicator in simple_indicators):
            return "simple"

        if (any(indicator in message_lower for indicator in complex_indicators) or
            has_multiple_parts or question_marks > 1 or word_count > 20):
            return "complex"

        if any(indicator in message_lower for indicator in medium_indicators):
            return "medium"

        # Default to simple for short, direct questions
        if word_count < 10:
            return "simple"

        return "medium"

    def _get_generation_config(self, message: str, has_rag_context: bool = False):
        """
        Get generation configuration including thinking budget based on query complexity.

        Args:
            message: User's message
            has_rag_context: Whether RAG context is being used

        Returns:
            GenerateContentConfig with ThinkingConfig or None
        """
        if not self.thinking_enabled or self.provider != "google":
            return None

        # Assess query complexity
        complexity = self._assess_query_complexity(message)

        # Set thinking budget based on complexity
        if complexity == "complex":
            thinking_budget = self.thinking_budget_complex
        elif complexity == "simple":
            thinking_budget = self.thinking_budget_simple
        else:
            thinking_budget = self.thinking_budget_default

        # Increase budget if RAG context is involved (need to reason about relevance)
        if has_rag_context and complexity != "simple":
            thinking_budget = int(thinking_budget * 1.2)

        # Create config with ThinkingConfig
        config = self.genai_types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=2048,
            thinking_config=self.genai_types.ThinkingConfig(
                thinking_budget=thinking_budget,
                include_thoughts=False  # Set to True if you want to see reasoning process
            )
        )

        print(f"[LLM] CoT enabled: {complexity} complexity, budget: {thinking_budget}")

        return config

    async def generate_response(
        self,
        message: str,
        context: Optional[TranscriptContext] = None
    ) -> str:
        """
        Generate an LLM response to a user message with optional context.
        Works with configured provider (Google or Llama).

        Args:
            message: User's message
            context: Optional student transcript context

        Returns:
            Generated response from the LLM

        Raises:
            ValueError: If API call fails
        """
        try:
            # Build system prompt with context
            system_prompt = self._build_system_prompt(context)

            # Check if question is vague
            if self._is_vague_question(message):
                clarifying_instruction = "\n\nIMPORTANT: This question is vague. Ask the student to clarify what specific help they need."
                system_prompt += clarifying_instruction

            # Check if question is program-related and use RAG for better context
            program_rag_context = self._get_program_context_from_rag(message)
            has_rag_context = program_rag_context is not None

            if program_rag_context:
                system_prompt += f"\n\n{program_rag_context}"
                print(f"[LLM] Using RAG context for program question")

            # Get generation config and complexity assessment
            generation_config = self._get_generation_config(message, has_rag_context)

            # Add explicit Chain of Thought instruction for complex queries
            complexity = self._assess_query_complexity(message)
            cot_instruction = ""
            if self.thinking_enabled and complexity in ["complex", "medium"]:
                if complexity == "complex":
                    cot_instruction = """

REASONING INSTRUCTIONS:
Before providing your final answer, think through the following steps:
1. Break down what the student is really asking
2. Identify which pieces of information are most relevant
3. Consider how different pieces of information relate to each other
4. Verify your reasoning against the provided data
5. Formulate a clear, accurate answer

Think step-by-step, but provide only your final answer to the student (don't show your reasoning steps unless they ask for an explanation)."""
                else:  # medium complexity
                    cot_instruction = """

REASONING INSTRUCTIONS:
Think through which information is most relevant to answer this question accurately before responding."""

            # Create message with system context and CoT instruction
            full_message = f"{system_prompt}{cot_instruction}\n\nStudent Question: {message}"

            # Generate response using configured provider
            if self.provider == "google":
                try:
                    # Use new API with thinking support
                    if generation_config:
                        response = self.genai_client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=full_message,
                            config=generation_config
                        )
                    else:
                        response = self.genai_client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=full_message
                        )

                    # Extract text from response
                    response_text = ""
                    if response and hasattr(response, 'candidates') and response.candidates:
                        candidate = response.candidates[0]
                        if hasattr(candidate, 'content') and candidate.content:
                            if hasattr(candidate.content, 'parts') and candidate.content.parts:
                                for part in candidate.content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        # Skip thoughts, only include actual response
                                        if not (hasattr(part, 'thought') and part.thought):
                                            response_text += part.text

                    # Fallback: try to get text directly from response
                    if not response_text and hasattr(response, 'text'):
                        response_text = response.text

                    if not response_text:
                        raise ValueError("Empty response from Gemini")
                    return response_text
                except ValueError as e:
                    # Check if it's a safety filter issue
                    if "safety_ratings" in str(e):
                        print(f"[WARNING] [LLM] Response blocked by safety filter")
                        print(f"   Error: {str(e)}")
                        print(f"   Message: {message[:100]}...")
                        # Try again without student context in case that's the issue
                        if context:
                            print(f"   Retrying without full context...")
                            retry_message = f"{system_prompt}\n\nStudent Question: {message}"
                            try:
                                retry_response = self.llm_backend.generate_content(retry_message)
                                if retry_response.text:
                                    return retry_response.text
                            except:
                                pass
                        # Return a friendly message when content is filtered
                        return "I apologize, but I'm unable to provide a response to that query due to content safety guidelines. Could you please rephrase your question?"
                    raise
            elif self.provider == "llama":
                # Llama service handles async internally
                response = await self.llm_backend.generate_response(message, system_prompt)
                if not response:
                    raise ValueError("Empty response from Llama")
                return response
            else:
                raise ValueError(f"Unknown provider: {self.provider}")

        except ValueError as e:
            # Check if it's already been handled (e.g., safety filter)
            if "unable to provide a response" in str(e):
                raise
            raise ValueError(f"LLM response generation failed: {str(e)}")
        except Exception as e:
            raise ValueError(f"LLM response generation failed: {str(e)}")

    def _get_program_context_from_rag(self, message: str) -> Optional[str]:
        """
        Check if question is program-related and retrieve context from RAG.

        Args:
            message: User's question

        Returns:
            RAG context if program-related, None otherwise
        """
        # Keywords that indicate program-related questions
        program_keywords = [
            "course", "courses",
            "requirement", "requirements",
            "program", "specialization", "concentration",
            "credits", "credit",
            "capstone", "core",
            "elective", "electives",
            "mis5", "mis4", "mkt5", "mkt4", "obc5", "oie5",  # course codes
            "data analytics", "artificial intelligence", "user experience", "digital transformation", "information systems",
            "graduate", "masters", "master's"
        ]

        message_lower = message.lower()

        # Check if message contains program keywords
        is_program_related = any(keyword in message_lower for keyword in program_keywords)

        if not is_program_related:
            return None

        # Get RAG service and retrieve context
        try:
            rag_service = get_rag_service()
            context = rag_service.get_context_for_query(message, program_id="msit", top_k=3)
            return context
        except Exception as e:
            print(f"[WARNING] [RAG] Error retrieving context: {str(e)}")
            return None

    def _format_context_for_logging(self, context: Optional[TranscriptContext]) -> str:
        """
        Format context for logging purposes.

        Args:
            context: Student context

        Returns:
            Formatted context string
        """
        if not context:
            return "No context"

        parts = []
        if context.student_name:
            parts.append(f"Student: {context.student_name}")
        if context.gpa is not None:
            parts.append(f"GPA: {context.gpa}")
        if context.program:
            parts.append(f"Program: {context.program}")
        if context.course_count is not None:
            parts.append(f"Courses: {context.course_count}")

        return ", ".join(parts) if parts else "No context"
