#!/usr/bin/env python3
"""
Debug script to see exactly what JSON the Intent Agent is returning from Gemini.
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from langchain.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from app.schemas.chat import IntentType

# Verify API key
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("✗ GOOGLE_API_KEY not set")
    sys.exit(1)

print("✓ GOOGLE_API_KEY is set")

# Build the intent prompt
def _intent_options() -> str:
    return ", ".join([intent.value for intent in IntentType])

INTENT_PROMPT_TEMPLATE = (
    "You are an intent classification agent for the WPI Business School chatbot.\n"
    "Identify the student's intent using these labels: [<<LABELS>>].\n\n"
    "Respond with ONLY a valid JSON object (no markdown, no extra text) using this exact schema:\n"
    '{"intent": "LABEL", "confidence": 0.5, "secondary_intents": [], "requires_transcript": false, "rule_applicable": false, "suggested_response_type": "clarify"}\n\n'
    "Schema details:\n"
    '- intent: exactly one of [<<LABELS>>]\n'
    '- confidence: number between 0 and 1\n'
    '- secondary_intents: array of intent labels\n'
    '- requires_transcript: boolean\n'
    '- rule_applicable: boolean\n'
    '- suggested_response_type: one of ["db_template", "progress_template", "clarify", "llm"]\n\n'
    "CRITICAL: Output ONLY valid JSON, nothing else. No markdown, no backticks, no explanation.\n"
)

prompt_template = INTENT_PROMPT_TEMPLATE.replace("<<LABELS>>", _intent_options())

# Create LLM
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    max_output_tokens=256,
    google_api_key=api_key,
)

# Create prompt
prompt = ChatPromptTemplate.from_messages([
    ("system", prompt_template),
    ("human", "Question: {question}"),
])

chain = prompt | llm

# Test queries
test_queries = [
    "What are the MSIT program requirements?",
    "Tell me about MSBA courses",
    "What specializations are available?",
]

print("\n" + "="*80)
print("DEBUGGING INTENT AGENT JSON OUTPUT")
print("="*80)

for i, query in enumerate(test_queries, 1):
    print(f"\n[Test {i}] Query: {query}")
    print("-" * 80)

    try:
        response = chain.invoke({"question": query})

        # Extract text
        if isinstance(response, str):
            raw_text = response
        else:
            raw_text = getattr(response, "text", None) or getattr(response, "content", str(response))

        print(f"Raw response length: {len(raw_text)} characters")
        print(f"Raw response (first 500 chars):\n{raw_text[:500]}")
        print(f"Raw response (last 100 chars):\n...{raw_text[-100:]}")

        # Try to parse
        print("\nParsing attempt:")

        # Step 1: Clean markdown if present
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            print("  - Found markdown code block, removing...")
            cleaned = cleaned[3:]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.rstrip("`")

        # Step 2: Extract JSON
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = cleaned[start:end+1]
            print(f"  - Extracted JSON substring ({start}-{end})")
        else:
            candidate = cleaned
            print("  - No JSON braces found, using full text")

        print(f"\nCandidate for parsing ({len(candidate)} chars):\n{candidate}")

        # Step 3: Parse JSON
        try:
            data = json.loads(candidate)
            print("\n✓ JSON parsing SUCCESSFUL")
            print(f"Parsed data: {json.dumps(data, indent=2)}")

        except json.JSONDecodeError as e:
            print(f"\n✗ JSON parsing FAILED: {e}")
            print(f"  Position: {e.pos}")
            print(f"  Line: {e.lineno}, Column: {e.colno}")

            # Show context around error
            if e.pos is not None and e.pos < len(candidate):
                start_ctx = max(0, e.pos - 30)
                end_ctx = min(len(candidate), e.pos + 30)
                context = candidate[start_ctx:end_ctx]
                marker = " " * (e.pos - start_ctx) + "^"
                print(f"\nContext around error:")
                print(f"  {context}")
                print(f"  {marker}")

    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()

    print()
