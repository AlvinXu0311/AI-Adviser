"""
PDF Extraction Service for processing and extracting text from PDF transcripts.
Supports multiple providers: Google Gemini Vision API or Local Llama model.
"""
import os
import base64
import re
import json
from typing import Optional
from datetime import datetime
from ..schemas.transcript import (
    ExtractedTranscriptData,
    CourseInfo,
    ProgramInfo,
)


class PDFExtractionService:
    """Service for extracting and parsing transcript data from PDF files"""

    def __init__(self):
        """Initialize the PDF extraction service with configured provider"""
        self.provider = os.getenv("LLM_PROVIDER", "google").lower()

        if self.provider == "llama":
            from .llama_service import get_llama_service
            self.llm_backend = get_llama_service()
            print(f"[INFO] [PDF Extraction] Using Llama provider")
        elif self.provider == "google":
            import google.generativeai as genai
            self.llm_backend = genai.GenerativeModel('gemini-2.5-flash')
            print(f"[INFO] [PDF Extraction] Using Google Gemini provider")
        else:
            raise ValueError(f"Unknown LLM_PROVIDER: {self.provider}. Use 'google' or 'llama'")

    async def extract_text_from_pdf(self, pdf_base64: str) -> str:
        """
        Extract text from PDF using configured provider.
        Supports Google Gemini Vision API or Local Llama model.

        Args:
            pdf_base64: Base64 encoded PDF file

        Returns:
            Extracted text content from the PDF

        Raises:
            ValueError: If PDF is invalid or extraction fails
        """
        try:
            print("[PDF Extraction] Starting PDF extraction process...")

            # Create image part from base64 PDF
            pdf_data = base64.b64decode(pdf_base64)
            print(f"[PDF Extraction] Decoded PDF size: {len(pdf_data) / 1024:.2f} KB")
            print(f"[PDF Extraction] Base64 input length: {len(pdf_base64)} characters")

            if self.provider == "google":
                # Use Gemini Vision to extract text from PDF
                prompt = """
                Please extract all text from this academic transcript PDF.
                Return the complete text content maintaining the structure.
                Extract student name, ID, GPA, courses taken, program information if visible.
                """

                print("[PDF Extraction] Calling Gemini Vision API with model: gemini-2.5-flash")
                print(f"[PDF Extraction] Prompt: {prompt.strip()}")

                response = self.llm_backend.generate_content([
                    prompt,
                    {"mime_type": "application/pdf", "data": pdf_base64}
                ])

                if not response.text:
                    raise ValueError("Failed to extract text from PDF")

                extracted_text = response.text
                print(f"[PDF Extraction] Successfully extracted text from Gemini")

            elif self.provider == "llama":
                # Use Llama to extract text from PDF
                print("[PDF Extraction] Calling Llama model for PDF extraction")
                extracted_text = await self.llm_backend.extract_text_from_pdf_with_llama(pdf_base64)

            else:
                raise ValueError(f"Unknown provider: {self.provider}")

            print(f"[PDF Extraction] Extracted text length: {len(extracted_text)} characters")
            print(f"[PDF Extraction] Extracted text preview (first 500 chars):")
            print(f"   {extracted_text[:500]}...")

            return extracted_text

        except Exception as e:
            print(f"[PDF Extraction] Error during extraction: {str(e)}")
            raise ValueError(f"PDF text extraction failed: {str(e)}")

    def format_extracted_text_with_regex(self, raw_text: str) -> Optional[ExtractedTranscriptData]:
        """
        Fast regex-based extraction and formatting of transcript data.
        Falls back to LLM if regex doesn't extract enough information.

        Args:
            raw_text: Raw extracted text from PDF

        Returns:
            Structured transcript data if successful, None if regex extraction is incomplete
        """
        try:
            print("\n📍 [PDF Processing] STEP 2A: Trying fast REGEX extraction first...")

            data = ExtractedTranscriptData(raw_text=raw_text)
            extraction_confidence = 0

            # Extract student name - try multiple patterns
            name_patterns = [
                r"(?:student\s+)?name[:\s]*([A-Za-z\s]+?)(?:\n|$)",
                r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b"
            ]
            for pattern in name_patterns:
                match = re.search(pattern, raw_text, re.IGNORECASE | re.MULTILINE)
                if match:
                    candidate = match.group(1).strip()
                    if len(candidate.split()) >= 2 and len(candidate) > 5:
                        data.student_name = candidate
                        extraction_confidence += 1
                        print(f"   [INFO] Found name: {data.student_name}")
                        break

            # Extract student ID
            id_patterns = [
                r"(?:student\s+)?id[:\s]*([A-Z0-9]{8,10})",
                r"\b([0-9]{9})\b",
                r"\b([AB]\d{8})\b"
            ]
            for pattern in id_patterns:
                match = re.search(pattern, raw_text, re.IGNORECASE)
                if match:
                    data.student_id = match.group(1).strip()
                    extraction_confidence += 1
                    print(f"   [INFO] Found ID: {data.student_id}")
                    break

            # Extract GPA - multiple patterns with improved robustness
            gpa_patterns = [
                r"(?:cumulative\s+)?gpa[:\s]*(\d+\.?\d{0,2})",
                r"grade\s+point\s+average[:\s]*(\d+\.?\d{0,2})",
                r"gpa[:\s]+(\d+\.?\d{0,2})\s*(?:/|out\s+of)?\s*(?:4\.0)?",
                r"cumulative[:\s]*(\d+\.?\d{0,2})",
                r"overall\s+gpa[:\s]*(\d+\.?\d{0,2})",
                r"(?:current|term)\s+gpa[:\s]*(\d+\.?\d{0,2})"
            ]
            for pattern in gpa_patterns:
                match = re.search(pattern, raw_text, re.IGNORECASE | re.MULTILINE)
                if match:
                    try:
                        gpa = float(match.group(1))
                        if 0.0 <= gpa <= 4.0:
                            data.gpa = gpa
                            extraction_confidence += 1
                            print(f"   [INFO] Found GPA: {data.gpa}")
                            break
                    except ValueError:
                        pass

            # Extract program
            program_patterns = [
                r"(?:program|degree)[:\s]*([^\n]+?(?:MS|BS|PhD|Master|Bachelor).*?)(?:\n|$)",
                r"(?:MS|BS|PhD|Master|Bachelor)\s+(?:in\s+)?([A-Za-z\s]+?)(?:\s*\(|$|\n)"
            ]
            for pattern in program_patterns:
                match = re.search(pattern, raw_text, re.IGNORECASE)
                if match:
                    program_name = match.group(1).strip()
                    if program_name and len(program_name) > 3:
                        data.program_info = ProgramInfo(program_name=program_name)
                        extraction_confidence += 1
                        print(f"   [INFO] Found program: {program_name}")
                        break

            # Extract courses - try to find course patterns
            course_pattern = r"([A-Z]{2,4}\d{3,4})\s*[-:]?\s*([^\n]{10,50}?)\s*(\d+\.?\d*)\s*(?:credits?)?\s*([A-F][+-]?)?"
            courses = re.findall(course_pattern, raw_text)
            if courses:
                data.completed_courses = []
                for code, name, credits, grade in courses:
                    if code.strip() and name.strip():
                        course = CourseInfo(
                            course_code=code.strip(),
                            course_name=name.strip(),
                            credits=float(credits),
                            grade=grade.strip() if grade else None
                        )
                        data.completed_courses.append(course)
                if data.completed_courses:
                    extraction_confidence += 1
                    print(f"   [INFO] Found {len(data.completed_courses)} courses")

            # Return data only if we found enough info, otherwise fallback to LLM
            # IMPORTANT: Courses are critical - if no courses found, use LLM
            if extraction_confidence >= 3 and data.completed_courses:  # At least 3 key fields + courses
                print(f"   [INFO] [REGEX] Success! Confidence: {extraction_confidence}/5 | Courses: {len(data.completed_courses)}")
                return data
            else:
                missing = []
                if extraction_confidence < 3:
                    missing.append(f"only {extraction_confidence}/5 fields")
                if not data.completed_courses:
                    missing.append("no courses found")
                print(f"   [WARNING] [REGEX] Incomplete extraction ({', '.join(missing)}). Will use LLM...")
                return None

        except Exception as e:
            print(f"   [WARNING] [REGEX] Error during regex extraction: {str(e)}")
            return None

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
            print("\n📍 [PDF Processing] STEP 2: Using LLM (Google Gemini) to format extracted text")

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
            "grade": "Grade earned (A, B, C, D, F, or with +/-, or null if not shown)"
        }},
        ...more courses...
    ],
    "current_courses": [
        {{
            "course_code": "Exact course code",
            "course_name": "Exact course name",
            "credits": 3.0
        }},
        ...more courses...
    ]
}}

EXTRACTION GUIDELINES:
1. GPA Extraction (CRITICAL - often clearly labeled):
   - Look for: "GPA:", "Cumulative GPA:", "Overall GPA:", "Current GPA:", "GPA: X.XX / 4.0"
   - Extract the numeric value only (3.71, 3.5, 2.75, etc.)
   - Must be between 0.0 and 4.0

2. Course Extraction (Find EVERY course):
   - Look for course code patterns: All caps + numbers (MIS581, IT504, MBA502, CS101, etc.)
   - For each course, find: code, name, credits, and grade (if shown)
   - Include BOTH completed and current courses
   - Extract grades exactly as shown (A+, A, A-, B+, B, B-, C+, C, C-, D+, D, D-, F, or numeric)
   - Extract credits as numbers (3.0, 4.0, etc.)

3. Student Info:
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

            if self.provider == "google":
                print("[LLM Formatting] Calling Gemini to format transcript data...")
                response = self.llm_backend.generate_content(formatting_prompt)
            elif self.provider == "llama":
                print("[LLM Formatting] Calling Llama to format transcript data...")
                response = self.llm_backend.format_extracted_text_with_llama(raw_text)
                # Llama service returns ExtractedTranscriptData directly, not a response object
                return response
            else:
                raise ValueError(f"Unknown provider: {self.provider}")

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

            print(f"[INFO] [LLM Formatting] Parsing LLM response...")
            print(f"   Response length: {len(json_text)} characters")

            try:
                formatted_data = json.loads(json_text)
            except json.JSONDecodeError as e:
                print(f"[WARN] [LLM Formatting] Initial JSON parse failed: {e}")
                print(f"[WARN] [LLM Formatting] Attempting JSON repair...")
                
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
                    print("[INFO] [LLM Formatting] JSON repair successful")
                except json.JSONDecodeError as e2:
                    print(f"[ERROR] [LLM Formatting] JSON repair failed: {e2}")
                    print(f"[DEBUG] Problematic JSON:\n{json_text[:500]}...")
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
                        print(f"   [COURSE] {course.course_code}: {course.course_name} | Credits: {course.credits} | Grade: {grade or 'NOT FOUND'}")

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
                        print(f"   [CURRENT] {course.course_code}: {course.course_name} | Credits: {course.credits}")

            print("[INFO] [LLM Formatting] Successfully formatted transcript data with LLM")
            return transcript_data

        except json.JSONDecodeError as e:
            print(f"[ERROR] [LLM Formatting] Failed to parse LLM response as JSON: {str(e)}")
            raise ValueError(f"Invalid JSON response from LLM: {str(e)}")
        except Exception as e:
            print(f"[ERROR] [LLM Formatting] Error during LLM formatting: {str(e)}")
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
            print("\n" + "="*80)
            print("[PDF Processing] Starting complete PDF processing pipeline")
            print("[PDF Processing] Using Google Gemini for accurate extraction of all transcript data")
            print("="*80)

            # Step 1: Extract text from PDF using Gemini Vision
            print("\n [PDF Processing] STEP 1: Extracting text from PDF using Google Gemini Vision API")
            extracted_text = await self.extract_text_from_pdf(pdf_base64)

            # Step 2: Use Google Gemini LLM for comprehensive data extraction
            # This ensures complete extraction of:
            # - All courses (completed and current)
            # - All grades for each course
            # - GPA and student information
            # - Credits for each course
            print("\n [PDF Processing] STEP 2: Using Google Gemini LLM for comprehensive transcript parsing")
            print("[PDF Processing] This will extract: student info, GPA, all courses, grades, credits")
            transcript_data = self.format_extracted_text_with_llm(extracted_text)

            # Note: Context storage is handled by the API layer (transcript.py) with session_id
            # This service only extracts data, it doesn't manage session context

            # Summary
            print("\n" + "="*80)
            print("[INFO] [PDF Processing] FINAL SUMMARY")
            print("="*80)
            print(f"   [INFO] Student Name: {transcript_data.student_name or 'N/A'}")
            print(f"   [INFO] Student ID: {transcript_data.student_id or 'N/A'}")
            print(f"   [INFO] GPA: {transcript_data.gpa or 'N/A'}")
            print(f"   [INFO] Program: {transcript_data.program_info.program_name if transcript_data.program_info else 'N/A'}")
            print(f"   [INFO] Completed Courses: {len(transcript_data.completed_courses) if transcript_data.completed_courses else 0}")
            print(f"   [INFO] Current Courses: {len(transcript_data.current_courses) if transcript_data.current_courses else 0}")
            print(f"   [INFO] Raw Text Length: {len(transcript_data.raw_text) if transcript_data.raw_text else 0} characters")
            print("="*80 + "\n")

            return transcript_data

        except Exception as e:
            print(f"\n[ERROR] [PDF Processing] FATAL ERROR: {str(e)}")
            print("="*80 + "\n")
            raise ValueError(f"PDF processing failed: {str(e)}")
