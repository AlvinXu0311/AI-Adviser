"""
Llama Service for local LLM operations using Ollama.
Provides an alternative to Google Gemini API using locally-run Llama3.1 model.
Supports both PDF text extraction and chat-based LLM interactions.
"""
import os
import json
import base64
import requests
from typing import Optional
from ..schemas.transcript import ExtractedTranscriptData, CourseInfo, ProgramInfo


class LlamaService:
    """Service for LLM interactions using local Llama3.1 model via Ollama"""

    def __init__(self):
        """Initialize the Llama service"""
        self.api_url = os.getenv("LLAMA_API_URL", "http://localhost:11434/api")
        self.model_name = os.getenv("LLAMA_MODEL_NAME", "llama3.1:8b")
        self.conversation_history = []

        # Test connection
        self._test_connection()

    def _test_connection(self) -> bool:
        """
        Test connection to Ollama service.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = requests.get(f"{self.api_url}/tags", timeout=5)
            if response.status_code == 200:
                print(f"[INFO] [Llama] Connected to Ollama at {self.api_url}")
                models = response.json().get("models", [])
                available_models = [m.get("name") for m in models]
                print(f"   Available models: {available_models}")

                # Check if our model is available
                if any(self.model_name in m for m in available_models):
                    print(f"   [INFO] Model '{self.model_name}' is available")
                else:
                    print(f"   [WARNING]  Model '{self.model_name}' not found. Available: {available_models}")
                return True
            else:
                print(f"[WARNING] [Llama] Failed to connect to Ollama: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"[WARNING] [Llama] Connection failed: {str(e)}")
            print(f"   Make sure Ollama is running at {self.api_url}")
            print(f"   Install: https://ollama.ai")
            print(f"   Run: ollama run {self.model_name}")
            return False

    async def extract_text_from_pdf_with_llama(self, pdf_base64: str) -> str:
        """
        Extract text from PDF using Llama (works with text-based PDFs).
        Note: This requires the PDF to be text-based, not image-based.
        For image-heavy PDFs, use Gemini instead.

        Args:
            pdf_base64: Base64 encoded PDF file

        Returns:
            Extracted text content from the PDF

        Raises:
            ValueError: If PDF extraction fails
        """
        try:
            print("[Llama PDF] Starting PDF text extraction with Llama...")

            # Decode base64 to get PDF bytes
            pdf_data = base64.b64decode(pdf_base64)
            print(f"[Llama PDF] Decoded PDF size: {len(pdf_data) / 1024:.2f} KB")

            # Try to extract text using pdfplumber via Llama instructions
            # This is a workaround since Llama can't directly read PDFs
            # For better results, consider using PyPDF2 locally

            prompt = """
            I will provide PDF content as text. Please extract the following information:
            1. Student Name
            2. Student ID
            3. GPA
            4. All courses taken with their codes, names, credits, and grades
            5. Program information if available

            Format the output as a structured text with clear sections.
            Make sure to preserve all course information exactly as provided.
            """

            print("[Llama PDF] Calling Llama for PDF text extraction...")
            response = self._call_llama(prompt, stream=False)

            if not response:
                raise ValueError("Failed to extract text from PDF with Llama")

            print(f"[Llama PDF] Successfully extracted text")
            print(f"[Llama PDF] Extracted text length: {len(response)} characters")
            print(f"[Llama PDF] Text preview (first 500 chars):")
            print(f"   {response[:500]}...")

            return response

        except Exception as e:
            print(f"[Llama PDF] Error during extraction: {str(e)}")
            raise ValueError(f"PDF text extraction with Llama failed: {str(e)}")

    def format_extracted_text_with_llama(self, raw_text: str) -> Optional[ExtractedTranscriptData]:
        """
        Format extracted text into structured transcript data using Llama.

        Args:
            raw_text: Raw extracted text from PDF

        Returns:
            Structured ExtractedTranscriptData or None if extraction fails

        Raises:
            ValueError: If formatting fails
        """
        try:
            print("[Llama Format] Starting transcript formatting with Llama...")

            prompt = f"""
            Parse this academic transcript text and extract the following information.
            Return ONLY valid JSON with no markdown formatting or code blocks.

            Extract:
            1. student_name (string)
            2. student_id (string)
            3. gpa (float)
            4. program (string)
            5. courses (list of objects with: code, name, credits (int), grade)
            6. current_courses (list of objects with: code, name, credits (int))

            Return format:
            {{
                "student_name": "...",
                "student_id": "...",
                "gpa": 3.5,
                "program": "...",
                "courses": [
                    {{"code": "CODE", "name": "Course Name", "credits": 3, "grade": "A"}},
                    ...
                ],
                "current_courses": [
                    {{"code": "CODE", "name": "Course Name", "credits": 3}},
                    ...
                ]
            }}

            IMPORTANT: Return ONLY the JSON object, no other text.
            If a field is not found, use appropriate defaults (empty string for strings, 0.0 for gpa, [] for lists).

            Transcript text:
            {raw_text}
            """

            response = self._call_llama(prompt, stream=False)
            print(f"[Llama Format] Llama response length: {len(response)} characters")
            print(f"[Llama Format] Response preview:")
            print(f"   {response[:300]}...")

            # Parse JSON response
            try:
                # Try to extract JSON from response (in case there's extra text)
                start_idx = response.find('{')
                end_idx = response.rfind('}') + 1

                if start_idx == -1 or end_idx <= start_idx:
                    raise ValueError("No JSON found in Llama response")

                json_str = response[start_idx:end_idx]
                data = json.loads(json_str)

                print("[Llama Format] Successfully parsed JSON from Llama response")

                # Validate and create ExtractedTranscriptData
                courses = []
                for course_data in data.get("courses", []):
                    course = CourseInfo(
                        code=course_data.get("code", ""),
                        name=course_data.get("name", ""),
                        credits=int(course_data.get("credits", 0)),
                        grade=course_data.get("grade", "")
                    )
                    courses.append(course)

                current_courses = []
                for course_data in data.get("current_courses", []):
                    course = CourseInfo(
                        code=course_data.get("code", ""),
                        name=course_data.get("name", ""),
                        credits=int(course_data.get("credits", 0)),
                        grade=""
                    )
                    current_courses.append(course)

                result = ExtractedTranscriptData(
                    student_name=data.get("student_name", ""),
                    student_id=data.get("student_id", ""),
                    gpa=float(data.get("gpa", 0.0)),
                    program=data.get("program", ""),
                    courses=courses,
                    current_courses=current_courses
                )

                print(f"[Llama Format] Formatted: {result.student_name} | GPA: {result.gpa} | Courses: {len(courses)}")
                return result

            except json.JSONDecodeError as e:
                print(f"[Llama Format] JSON parse error: {str(e)}")
                print(f"[Llama Format] Response: {response}")
                raise ValueError(f"Failed to parse Llama JSON response: {str(e)}")

        except Exception as e:
            print(f"[Llama Format] Error during formatting: {str(e)}")
            raise ValueError(f"Text formatting with Llama failed: {str(e)}")

    async def generate_response(self, message: str, system_prompt: str = "") -> str:
        """
        Generate an LLM response using Llama.

        Args:
            message: User's message
            system_prompt: Optional system prompt for context

        Returns:
            Generated response from Llama

        Raises:
            ValueError: If LLM call fails
        """
        try:
            print(f"[Llama Chat] Generating response for message: {message[:50]}...")

            # Build full prompt with system context
            if system_prompt:
                full_prompt = f"{system_prompt}\n\nUser Message: {message}"
            else:
                full_prompt = message

            response = self._call_llama(full_prompt, stream=False)

            if not response:
                raise ValueError("Empty response from Llama")

            print(f"[Llama Chat] Generated response: {len(response)} characters")
            return response

        except Exception as e:
            print(f"[Llama Chat] Error generating response: {str(e)}")
            raise ValueError(f"Llama response generation failed: {str(e)}")

    def _call_llama(self, prompt: str, stream: bool = False) -> str:
        """
        Make a request to Ollama Llama service.

        Args:
            prompt: The prompt to send to Llama
            stream: Whether to stream the response

        Returns:
            Generated text from Llama

        Raises:
            ValueError: If API call fails
        """
        try:
            endpoint = f"{self.api_url}/generate"

            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": stream,
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40
            }

            print(f"[Llama API] Calling {endpoint} with model {self.model_name}")

            response = requests.post(endpoint, json=payload, timeout=300)

            if response.status_code != 200:
                raise ValueError(f"Ollama API returned status {response.status_code}: {response.text}")

            if stream:
                # Streaming response
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        full_response += data.get("response", "")
                return full_response
            else:
                # Non-streaming response
                data = response.json()
                return data.get("response", "")

        except requests.exceptions.ConnectionError:
            print(f"[ERROR] [Llama] Cannot connect to Ollama at {self.api_url}")
            print(f"   Make sure Ollama is running: ollama serve")
            print(f"   Pull model: ollama pull {self.model_name}")
            raise ValueError(f"Cannot connect to Ollama at {self.api_url}")
        except Exception as e:
            print(f"[ERROR] [Llama] Error calling Ollama API: {str(e)}")
            raise ValueError(f"Ollama API call failed: {str(e)}")


# Global singleton instance
_llama_service: Optional[LlamaService] = None


def get_llama_service() -> LlamaService:
    """Get or create the global Llama service instance"""
    global _llama_service
    if _llama_service is None:
        _llama_service = LlamaService()
    return _llama_service
