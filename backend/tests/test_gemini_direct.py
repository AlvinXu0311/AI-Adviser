#!/usr/bin/env python3
"""Direct test of Gemini API without LangChain"""
import os
import sys
import time
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("ERROR: GOOGLE_API_KEY not set")
    sys.exit(1)

print(f"Testing with API key: {api_key[:20]}...")
genai.configure(api_key=api_key)

# Test 1: Simple generation
print("\n=== Test 1: Simple generation ===")
model = genai.GenerativeModel("gemini-2.5-flash")
try:
    start = time.time()
    response = model.generate_content("Hello, what is 2+2?")
    elapsed = time.time() - start
    print(f"SUCCESS in {elapsed:.2f}s: {response.text}")
except Exception as e:
    print(f"FAILED: {e}")

# Test 2: JSON response
print("\n=== Test 2: JSON response (like intent agent) ===")
try:
    start = time.time()
    response = model.generate_content(
        'Respond with ONLY valid JSON: {"test": "value"}'
    )
    elapsed = time.time() - start
    print(f"SUCCESS in {elapsed:.2f}s: {response.text}")
except Exception as e:
    print(f"FAILED: {e}")

# Test 3: With temperature and token limit
print("\n=== Test 3: With temperature=0 and max_output_tokens=256 ===")
try:
    start = time.time()
    response = model.generate_content(
        'Respond with JSON: {"intent": "test"}',
        generation_config=genai.types.GenerationConfig(
            temperature=0,
            max_output_tokens=256,
        )
    )
    elapsed = time.time() - start
    print(f"SUCCESS in {elapsed:.2f}s: {response.text}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== All direct API tests complete ===")
