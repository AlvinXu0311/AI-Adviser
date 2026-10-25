"""
PDF Extraction Service for processing and extracting text from PDF transcripts.
Uses Gemini to read the PDF and to structure the extracted text.
"""
import asyncio
import logging
import re
import json
from datetime import datetime
from ..config import gemini_model, legacy_request_options
from ..observability import traced_opaque
from ..schemas.transcript import (
    ExtractedTranscriptData,
    CourseInfo,
    ProgramInfo,
)

# Transcripts are student records: log sizes and counts only, never names, IDs, grades or text
logger = logging.getLogger(__name__)


class PDFExtractionService:
    """Service for extracting and parsing transcript data from PDF files"""

    def __init__(self):
        """Initialize the PDF extraction service with the Gemini model"""
        import google.generativeai as genai
        self.llm_backend = genai.GenerativeModel(gemini_model())

    @traced_opaque(
        "transcript_ocr",
        describe_inputs=lambda i: {"pdf_base64_chars": len(i.get("pdf_base64") or "")},
        describe_outputs=lambda text: {"text_chars": len(text or "")},
    )
    async def extract_text_from_pdf(self, pdf_base64: str) -> str:
        """
        Extract text from PDF using Gemini Vision.

        Args:
            pdf_base64: Base64 encoded PDF file

        Returns:
            Extracted text content from the PDF

        Raises:
            ValueError: If PDF is invalid or extraction fails
        """
        try:
            logger.info("Extracting transcript text with %s (%d base64 chars)", gemini_model(), len(pdf_base64))

            # Use Gemini Vision to extract text from PDF
            prompt = """
            Please extract all text from this academic transcript PDF.
            Return the complete text content maintaining the structure.
            Extract student name, ID, GPA, courses taken, program information if visible.
            """

            # Blocking SDK call: run it in a worker thread so the event loop keeps serving requests
            response = await asyncio.to_thread(
                self.llm_backend.generate_content,
                [prompt, {"mime_type": "application/pdf", "data": pdf_base64}],
                request_options=legacy_request_options(),
            )

            if not response.text:
                raise ValueError("Failed to extract text from PDF")

            extracted_text = response.text
            logger.info("Extracted %d characters of transcript text", len(extracted_text))
            return extracted_text

        except Exception as e:
            raise ValueError(f"PDF text extraction failed: {str(e)}")

    @traced_opaque(
        "transcript_structuring",
        describe_inputs=lambda i: {"raw_text_chars": len(i.get("raw_text") or "")},
        describe_outputs=lambda d: {
            "completed_courses": len(d.completed_courses or []),
            "current_courses": len(d.current_courses or []),
            "gpa_found": d.gpa is not None,
        },
    )
    def format_extracted_text_with_llm(self, raw_text: str) -> ExtractedTranscriptData:
        """
        Use LLM to format and structure the extracted PDF text.
        Much more reliable than regex parsing.

        Args:
            raw_text: Raw extracted text from PDF

        Returns:
            Structured transcript data formatted by LLM

        Raises:
            ValueError: If LLM formatting fails
        """
        try:

            formatting_prompt = f"""
You are an expert at parsing academic transcripts from universities.
Use your vision and language understanding to extract COMPLETE and ACCURATE data.

I have extracted raw text from an academic transcript PDF.
Your job is to carefully analyze this text and extract ALL information that appears in the transcript.

CRITICAL INSTRUCTIONS:
- Extract EXACTLY what appears in the document. Do NOT infer, guess, or make up data.
- If information is not explicitly stated, set it to null
- Be thorough: Extract EVERY course listed with ALL its details
- Find and extract all grades, credits, and course codes accurately
- DISTINGUISH between completed courses (with grades) and current courses (in progress, no final grade)

Return the data in this JSON format ONLY (no markdown code blocks, just pure JSON):
{{
    "student_name": "Full legal name exactly as shown on transcript (or null if not found)",
    "student_id": "Student ID number or A-ID exactly as shown (or null if not found)",
    "gpa": numeric GPA value (e.g., 3.71) or null,
    "program_info": {{
        "program_name": "Exact program name from transcript (or null)",
        "enrollment_date": "Date in YYYY-MM-DD format if stated, or null"
    }},
    "completed_courses": [
        {{
            "course_code": "Exact course code (e.g., MIS581, IT504, CS101)",
            "course_name": "Exact course name/title",
            "credits": 3.0,
            "grade": "Grade earned (A, B, C, D, F, or with +/-, or null if not shown)",
            "semester": "Semester if shown (e.g., Fall 2024, Spring 2025)"
        }},
        ...more completed courses with grades...
    ],
    "current_courses": [
        {{
            "course_code": "Exact course code",
            "course_name": "Exact course name",
            "credits": 3.0,
            "semester": "Current semester if shown"
        }},
        ...courses currently being taken (in progress, no grade yet)...
    ]
}}

EXTRACTION GUIDELINES:
1. GPA Extraction (CRITICAL - often clearly labeled):
   - Look for: "GPA:", "Cumulative GPA:", "Overall GPA:", "Current GPA:", "GPA: X.XX / 4.0"
   - Extract the numeric value only (3.71, 3.5, 2.75, etc.)
   - Must be between 0.0 and 4.0

2. COMPLETED vs CURRENT Courses (VERY IMPORTANT):
   - COMPLETED courses: Have a final grade (A, B, C, D, F, etc.) - put in "completed_courses"
   - CURRENT courses: In progress, no final grade, status like "IP", "In Progress", "Enrolled", or just no grade - put in "current_courses"
   - Look for section headers like "Current Term", "In Progress", "Current Semester", "Enrolled Courses"
   - Courses listed for the current/latest semester without grades are likely current courses
   - If a course shows status like "IP", "In Progress", "Registered", or blank grade - it's a CURRENT course

3. Course Extraction (Find EVERY course):
   - Look for course code patterns: All caps + numbers (MIS581, IT504, MBA502, CS101, etc.)
   - For each course, find: code, name, credits, grade (if any), and semester
   - Extract grades exactly as shown (A+, A, A-, B+, B, B-, C+, C, C-, D+, D, D-, F, or numeric)
   - Extract credits as numbers (3.0, 4.0, etc.)

4. Student Info:
   - Name: Full legal name as shown
   - ID: Student ID or A-ID number
   - Program: Exact program name (MS in Information Technology, MBA, etc.)
   - Enrollment: Date if explicitly stated

VALIDATION:
- Return ONLY the JSON, no explanations or markdown
- GPA must be null or a number between 0.0-4.0
- All course codes must match the transcript exactly
- All course names must match the transcript exactly
- All grades must be valid letter grades (A-F with optional +/-)
- Return valid JSON that can be parsed without errors
- If no courses found, use empty array []

Here is the COMPLETE raw transcript text to analyze:
{raw_text}
"""

            response = self.llm_backend.generate_content(formatting_prompt, request_options=legacy_request_options())

            if not response.text:
                raise ValueError("LLM returned empty response")

            # Parse LLM response as JSON with robust cleaning
            json_text = response.text.strip()
            
            # Remove markdown code blocks if present
            if json_text.startswith("```"):
                # Handle ```json or just ```
                lines = json_text.split("\n")
                # Remove first line (```json or ```)
                lines = lines[1:]
                # Remove last line if it's just ```
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                json_text = "\n".join(lines).strip()
            
            # Additional cleanup for common LLM issues
            # Remove trailing commas before } or ]
            json_text = re.sub(r',(\s*[}\]])', r'\1', json_text)
            # Remove any non-JSON text before the first {
            first_brace = json_text.find('{')
            if first_brace > 0:
                json_text = json_text[first_brace:]
            # Remove any non-JSON text after the last }
            last_brace = json_text.rfind('}')
            if last_brace > 0 and last_brace < len(json_text) - 1:
                json_text = json_text[:last_brace + 1]

            try:
                formatted_data = json.loads(json_text)
            except json.JSONDecodeError as e:
                logger.warning("Transcript JSON parse failed (%s); attempting repair", e)
                # Try more aggressive cleanup
                # Replace single quotes with double quotes
                json_text_fixed = json_text.replace("'", '"')
                # Remove control characters
                json_text_fixed = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_text_fixed)
                # Fix unquoted keys
                json_text_fixed = re.sub(r'(\w+)(?=\s*:)', r'"\1"', json_text_fixed)
                # Remove duplicate quotes
                json_text_fixed = re.sub(r'""(\w+)""', r'"\1"', json_text_fixed)
                
                try:
                    formatted_data = json.loads(json_text_fixed)
                except json.JSONDecodeError as e2:
                    raise ValueError(f"Invalid JSON response from LLM: {str(e)}")

            # Convert JSON to ExtractedTranscriptData object
            transcript_data = ExtractedTranscriptData(
                raw_text=raw_text,
                student_name=formatted_data.get("student_name"),
                student_id=formatted_data.get("student_id"),
                gpa=formatted_data.get("gpa"),
            )

            # Parse program info
            if formatted_data.get("program_info"):
                program_info = formatted_data["program_info"]
                enrollment_date = None
                if program_info.get("enrollment_date"):
                    try:
                        enrollment_date = datetime.strptime(
                            program_info["enrollment_date"], "%Y-%m-%d"
                        ).date()
                    except (ValueError, TypeError):
                        pass

                transcript_data.program_info = ProgramInfo(
                    program_name=program_info.get("program_name"),
                    enrollment_date=enrollment_date
                )

            # Parse completed courses
            if formatted_data.get("completed_courses"):
                transcript_data.completed_courses = []
                for course_data in formatted_data["completed_courses"]:
                    if course_data.get("course_code") and course_data.get("course_name"):
                        grade = course_data.get("grade")
                        course = CourseInfo(
                            course_code=course_data["course_code"],
                            course_name=course_data["course_name"],
                            credits=float(course_data.get("credits", 0)),
                            grade=grade
                        )
                        transcript_data.completed_courses.append(course)

            # Parse current courses
            if formatted_data.get("current_courses"):
                transcript_data.current_courses = []
                for course_data in formatted_data["current_courses"]:
                    if course_data.get("course_code") and course_data.get("course_name"):
                        course = CourseInfo(
                            course_code=course_data["course_code"],
                            course_name=course_data["course_name"],
                            credits=float(course_data.get("credits", 0))
                        )
                        transcript_data.current_courses.append(course)

            return transcript_data

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from LLM: {str(e)}")
        except Exception as e:
            raise ValueError(f"LLM formatting failed: {str(e)}")

    async def process_pdf(self, pdf_base64: str) -> ExtractedTranscriptData:
        """
        Complete PDF processing pipeline:
        1. Extract text from PDF using Gemini Vision
        2. Format and structure using LLM (Google Gemini)
        3. Store in shared context cache

        Args:
            pdf_base64: Base64 encoded PDF file

        Returns:
            Extracted and parsed transcript data with complete course details and grades

        Raises:
            ValueError: If processing fails
        """
        try:
            # Step 1: Extract text from PDF using Gemini Vision
            extracted_text = await self.extract_text_from_pdf(pdf_base64)

            # Step 2: Use Google Gemini LLM for comprehensive data extraction
            # This ensures complete extraction of:
            # - All courses (completed and current)
            # - All grades for each course
            # - GPA and student information
            # - Credits for each course
            transcript_data = await asyncio.to_thread(self.format_extracted_text_with_llm, extracted_text)

            # Note: Context storage is handled by the API layer (transcript.py) with session_id
            # This service only extracts data, it doesn't manage session context
            logger.info(
                "Transcript parsed: %d completed, %d current courses, gpa %s, program %s",
                len(transcript_data.completed_courses or []),
                len(transcript_data.current_courses or []),
                "found" if transcript_data.gpa is not None else "missing",
                "found" if transcript_data.program_info else "missing",
            )
            return transcript_data

        except Exception as e:
            raise ValueError(f"PDF processing failed: {str(e)}")
