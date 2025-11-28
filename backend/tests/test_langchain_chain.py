#!/usr/bin/env python3
"""Test LangChain chain specifically"""
import os
import sys
import time
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from langchain.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("ERROR: GOOGLE_API_KEY not set")
    sys.exit(1)

print(f"Testing LangChain with API key: {api_key[:20]}...")

# Create LLM exactly like in intent_agent.py
print("\n=== Creating LLM ===")
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    max_output_tokens=256,
    google_api_key=api_key,
)
print("LLM created successfully")

# Create prompt exactly like in intent_agent.py
print("\n=== Creating prompt template ===")
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant. Respond with JSON."),
    ("human", "Question: {question}"),
])
print("Prompt created successfully")

# Create chain
print("\n=== Creating chain ===")
chain = prompt | llm
print("Chain created successfully")

# Test 1: Synchronous invoke
print("\n=== Test 1: Synchronous invoke ===")
try:
    start = time.time()
    result = chain.invoke({"question": "What is 2+2?"})
    elapsed = time.time() - start
    print(f"SUCCESS in {elapsed:.2f}s")
    print(f"Result type: {type(result)}")
    print(f"Result: {result}")
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Async invoke
print("\n=== Test 2: Async ainvoke ===")
async def test_async():
    try:
        start = time.time()
        result = await chain.ainvoke({"question": "What is 2+2?"})
        elapsed = time.time() - start
        print(f"SUCCESS in {elapsed:.2f}s")
        print(f"Result type: {type(result)}")
        print(f"Result: {result}")
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test_async())

# Test 3: With asyncio.wait_for timeout
print("\n=== Test 3: With asyncio.wait_for timeout (5 seconds) ===")
async def test_timeout():
    try:
        start = time.time()
        result = await asyncio.wait_for(
            chain.ainvoke({"question": "What is 2+2?"}),
            timeout=5.0
        )
        elapsed = time.time() - start
        print(f"SUCCESS in {elapsed:.2f}s")
        print(f"Result: {result}")
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"TIMEOUT after {elapsed:.2f}s")
    except Exception as e:
        elapsed = time.time() - start
        print(f"FAILED after {elapsed:.2f}s: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test_timeout())

# Test 4: With executor (like current fix)
print("\n=== Test 4: With executor + asyncio.wait_for ===")
async def test_executor():
    try:
        start = time.time()
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, chain.invoke, {"question": "What is 2+2?"}),
            timeout=5.0
        )
        elapsed = time.time() - start
        print(f"SUCCESS in {elapsed:.2f}s")
        print(f"Result: {result}")
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"TIMEOUT after {elapsed:.2f}s")
    except Exception as e:
        elapsed = time.time() - start
        print(f"FAILED after {elapsed:.2f}s: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test_executor())

print("\n=== All LangChain tests complete ===")
