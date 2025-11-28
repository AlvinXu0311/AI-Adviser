#!/usr/bin/env python3
"""
Test the Intent Agent directly with the fixed prompt template.
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Load env first
from dotenv import load_dotenv
load_dotenv()

from app.agents.intent_agent import get_intent_agent

async def main():
    print("="*80)
    print("TESTING INTENT AGENT WITH FIXED PROMPT TEMPLATE")
    print("="*80)

    # Verify API key
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("✗ GOOGLE_API_KEY not set")
        return 1

    print("✓ GOOGLE_API_KEY is set\n")

    intent_agent = get_intent_agent()

    test_queries = [
        "What are the MSIT program requirements?",
        "Tell me about MSBA courses and specializations",
        "What specializations are available in MSM?",
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"[Test {i}] Query: {query}")
        print("-" * 80)

        try:
            result = await intent_agent.classify(query)
            print(f"✓ Intent classification successful")
            print(f"  Intent: {result.intent.value}")
            print(f"  Confidence: {result.confidence}")
            print(f"  Requires transcript: {result.requires_transcript}")
            print(f"  Secondary intents: {[i.value for i in result.secondary_intents]}")
            print()

        except Exception as e:
            print(f"✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return 1

    print("="*80)
    print("✓ ALL TESTS PASSED - Intent Agent is working correctly")
    print("="*80)
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
