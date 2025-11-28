"""
LLM Service for generating context-aware responses.
Supports multiple providers: Google Gemini API or Local Llama3.1 model.
Integrates with RAG service for program-related questions.
"""
import os
from typing import Optional
from ..schemas.chat import TranscriptContext
from .context_manager import get_context_manager
# DEPRECATED: RAG service no longer used - Database-First architecture
# from .rag_service import get_rag_service


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

CRITICAL INSTRUCTION - ANSWER ONLY WHAT IS ASKED:
Do NOT add unsolicited commentary, suggestions, or advice.
Do NOT discuss grades unless asked about specific grades.
Do NOT provide tips or strategies unless explicitly requested.
Do NOT add "notes" or "observations" about performance.
Do NOT provide general advice alongside the answer.

ANTI-HALLUCINATION RULES (MANDATORY):
1. ONLY use information from the "Program Information" section provided below
2. If information is NOT in the provided context, say "I don't have that information in my knowledge base"
3. DO NOT make up course names, codes, requirements, or program details
4. DO NOT infer or guess information that isn't explicitly stated
5. If asked about something not in your context, admit you don't know
6. ALWAYS cite specific details from the provided program information

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
- NEVER answer based on general knowledge about WPI or business programs
- ONLY answer based on the exact information provided to you

EXAMPLE:
WRONG: "Your progress is 12 credits completed out of 33 needed. I notice you have a C in MKT 565, so you might want to focus on stronger performance going forward."
RIGHT: "You have completed 12 credits out of 33 needed for the program."

WHEN INFORMATION IS MISSING:
WRONG: "The MS in IT program typically requires..."
RIGHT: "I don't have that specific information in my knowledge base. Would you like me to help with something else?"

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

    def _is_progress_question(self, message: str) -> bool:
        """
        Detect if the user is asking about their academic progress/graduation.

        Args:
            message: User's message

        Returns:
            True if message requests progress/graduation status
        """
        if not message:
            return False

        message_lower = message.lower()
        progress_indicators = [
            "progress",
            "process",
            "how am i doing",
            "how am i",
            "current progress",
            "what's my progress",
            "what is my progress",
            "am i on track",
            "what's left",
            "remaining requirements",
            "what's left for graduation",
            "what's left to graduate",
            "graduation status",
            "how close to graduation",
            "degree progress",
        ]

        return any(indicator in message_lower for indicator in progress_indicators)

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
        # Note: max_output_tokens includes thinking tokens, so set it high enough
        config = self.genai_types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=8000,  # Increased to accommodate thinking + actual response
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

            # If user explicitly asks about progress/graduation, instruct the LLM
            # to provide structured details: required, completed, current, remaining.
            if self._is_progress_question(message):
                progress_instruction = """

PROGRESS DETAIL GUIDELINES:
- If the student asks about progress or graduation, include these short sections (headings + concise bullets):
  1) Required / Program Requirements: List the core required courses or total credits needed (from program info).
  2) Completed: List required courses the student has completed (use transcript data).
  3) In Progress / Current: List courses currently in progress (use transcript data).
  4) Remaining / To Graduate: List remaining required courses or approximate credits left; if exact details are missing, say "I don't have that information in my knowledge base".
- Use only the data present in the provided transcript and program information; DO NOT infer or fabricate course codes, names, or requirements.
- Keep each section short (1-4 bullets) and end with total credits remaining if known.

"""
                system_prompt += progress_instruction

            # DEPRECATED: RAG retrieval no longer used - Database-First architecture
            # Program queries are now handled by the adviser_agent using database tool
            # program_id = self._detect_program_from_context(context)
            # program_rag_context = self._get_program_context_from_rag(message, program_id, force_retrieval=True)
            # has_rag_context = program_rag_context is not None

            # Set has_rag_context to False for Database-First approach
            has_rag_context = False

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

            # Safety check: log prompt length
            print(f"[LLM] Full prompt length: {len(full_message)} chars")
            if len(full_message) > 30000:
                print(f"[WARNING] [LLM] Prompt is very long ({len(full_message)} chars), may cause issues")

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

                    # Extract text from response - try multiple methods
                    response_text = ""

                    # Method 1: Try direct text attribute
                    if hasattr(response, 'text') and response.text:
                        response_text = response.text
                        print(f"[LLM] Extracted response using .text attribute")

                    # Method 2: Navigate through candidates structure
                    elif response and hasattr(response, 'candidates') and response.candidates:
                        print(f"[LLM] Attempting to extract from candidates structure")
                        candidate = response.candidates[0]

                        if hasattr(candidate, 'content') and candidate.content:
                            if hasattr(candidate.content, 'parts') and candidate.content.parts:
                                for part in candidate.content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        # Skip thoughts, only include actual response
                                        if not (hasattr(part, 'thought') and part.thought):
                                            response_text += part.text

                        # Fallback: try text attribute on candidate
                        if not response_text and hasattr(candidate, 'text'):
                            response_text = candidate.text

                    # Method 3: Try stringifying the response
                    if not response_text:
                        print(f"[LLM] WARNING: Could not extract text normally, inspecting response structure")
                        print(f"[LLM] Response type: {type(response)}")
                        print(f"[LLM] Response attributes: {dir(response)[:10]}...")

                        # Last resort: convert to string
                        if response:
                            response_str = str(response)
                            if len(response_str) > 50:  # If we got something substantial
                                print(f"[LLM] Using stringified response as fallback")
                                response_text = response_str

                    if not response_text:
                        print(f"[ERROR] [LLM] Empty response from Gemini after all extraction attempts")
                        print(f"[ERROR] [LLM] Response object: {response}")
                        raise ValueError("Empty response from Gemini")

                    print(f"[LLM] Successfully extracted response: {len(response_text)} chars")
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

    def _detect_program_from_context(self, context: Optional[TranscriptContext]) -> str:
        """
        Detect which program the student is enrolled in from their context.

        Args:
            context: Student transcript context

        Returns:
            Program ID (msit, msba, or msm), defaults to msit
        """
        if not context or not context.program:
            return "msit"  # Default

        program_lower = context.program.lower()

        # Map program names to IDs
        if any(keyword in program_lower for keyword in ["information technology", "ms in it", "msit", "m.s. in information technology"]):
            return "msit"
        elif any(keyword in program_lower for keyword in ["business analytics", "msba", "analytics", "m.s. in business analytics"]):
            return "msba"
        elif any(keyword in program_lower for keyword in ["management", "msm", "ms in management", "m.s. in management"]):
            return "msm"

        print(f"[LLM] Unknown program '{context.program}', defaulting to MSIT")
        return "msit"

    # DEPRECATED: RAG method no longer used - Database-First architecture
    # The adviser_agent.py now handles all program queries using the database tool directly
    # def _get_program_context_from_rag(self, message: str, program_id: str = "msit", force_retrieval: bool = False) -> Optional[str]:
    #     """
    #     Check if question is program-related and retrieve context from RAG.
    #     Can be forced to ALWAYS retrieve for maximum precision.
    #
    #     Args:
    #         message: User's question
    #         program_id: Program ID to search (msit, msba, msm)
    #         force_retrieval: If True, always attempts retrieval regardless of question type
    #
    #     Returns:
    #         RAG context if relevant found, None otherwise
    #     """
    #     # Expanded keywords that indicate program-related questions
    #     program_keywords = [
    #         # Course related
    #         "course", "courses", "class", "classes",
    #         # Requirements
    #         "requirement", "requirements", "need", "needs", "needed",
    #         "must", "should take", "have to take",
    #         # Program structure
    #         "program", "specialization", "concentration", "track",
    #         "credits", "credit", "credit hours",
    #         "capstone", "core", "foundation",
    #         "elective", "electives", "optional",
    #         # Course codes (expanded)
    #         "mis5", "mis4", "mkt5", "mkt4", "obc5", "oie5",
    #         "mis ", "mkt ", "obc ", "oie ",  # with space to catch MIS581, etc
    #         # Specializations
    #         "data analytics", "artificial intelligence", "user experience",
    #         "digital transformation", "information systems",
    #         "ai", "ux", "data", "analytics", "business intelligence",
    #         # Program questions
    #         "graduate", "masters", "master's", "degree",
    #         "curriculum", "coursework",
    #         # Planning questions
    #         "what should i take", "what can i take", "recommend",
    #         "next semester", "plan", "schedule",
    #         "which course", "what courses",
    #         # Completion questions
    #         "how many", "how much", "total",
    #         "finish", "complete", "graduation", "graduate"
    #     ]
    #
    #     message_lower = message.lower()
    #
    #     # Check if message contains program keywords
    #     is_program_related = any(keyword in message_lower for keyword in program_keywords)
    #
    #     # Also check for question patterns that need program info
    #     program_question_patterns = [
    #         r"what (courses?|classes?)",
    #         r"which (courses?|classes?)",
    #         r"(can|should|must) i take",
    #         r"requirements? (for|to)",
    #         r"how many (courses?|credits?)",
    #         r"tell me about.*program",
    #         r"what.*specialization",
    #     ]
    #
    #     import re
    #     if not is_program_related:
    #         is_program_related = any(re.search(pattern, message_lower) for pattern in program_question_patterns)
    #
    #     # If force_retrieval is True, ALWAYS attempt retrieval
    #     if not is_program_related and not force_retrieval:
    #         print(f"[RAG] Question not program-related, skipping RAG: '{message[:50]}...'")
    #         return None
    #
    #     if force_retrieval and not is_program_related:
    #         print(f"[RAG] Force retrieval enabled - attempting RAG even for non-program question")
    #
    #     # MANDATORY RAG retrieval
    #     try:
    #         if is_program_related or force_retrieval:
    #             print(f"[RAG] MANDATORY retrieval: '{message[:50]}...'")
    #             print(f"[RAG] Using program: {program_id.upper()}")
    #             rag_service = get_rag_service()
    #
    #             # Use improved BM25 search with higher top_k for better coverage
    #             context = rag_service.get_context_for_query(
    #                 message,
    #                 program_id=program_id,
    #                 top_k=5,  # Increased from 3 for better coverage
    #                 use_bm25=True  # Force BM25 for better ranking
    #             )
    #
    #             if not context or len(context.strip()) < 50:
    #                 print(f"[WARNING] [RAG] Retrieved context is empty or too short!")
    #
    #                 # If forced retrieval but nothing relevant found, provide general program overview
    #                 if force_retrieval:
    #                     print(f"[RAG] Providing general program overview as fallback")
    #                     program_info = rag_service.retrieve_program_info(program_id)
    #                     if program_info:
    #                         fallback_context = f"""
    # Program: {program_info.get('name')}
    # Total Credits: {program_info.get('total_credits')}
    # Overview: {program_info.get('overview')}
    #
    # Core Requirements:
    # - {len(program_info.get('core_courses', []))} core courses (9 credits)
    # - 2 specializations (18 credits total)
    # - Capstone requirement (6 credits)
    # """
    #                         return fallback_context
    #
    #                 # Return a fallback message
    #                 return "\n\nProgram Information: [No relevant program information found in knowledge base for this query]"
    #
    #             print(f"[RAG] Successfully retrieved {len(context)} chars of context")
    #             return context
    #
    #     except Exception as e:
    #         print(f"[ERROR] [RAG] Error retrieving context: {str(e)}")
    #         # Return error context so LLM knows to say "I don't know"
    #         return "\n\nProgram Information: [Error retrieving program information from knowledge base]"

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
