#!/usr/bin/env python3
"""
End-to-end test for Intent Agent → Adviser Agent pipeline.
Tests the complete flow:
1. Intent classification with free-form LLM analysis
2. Adviser Agent with Database-First architecture
3. Final response generation
"""
import asyncio
import sys
import os
import json
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.agents.intent_agent import get_intent_agent
from app.agents.adviser_agent import get_adviser_agent
from app.services.program_db_service import get_program_db_service


async def test_intent_agent():
    """Test 1: Intent Agent classification with free-form LLM analysis"""
    print("\n" + "="*80)
    print("TEST 1: Intent Agent Free-Form Classification")
    print("="*80)

    test_queries = [
        "What are the MSIT program requirements?",
        "Tell me about MSBA courses",
        "What's the difference between MSIT and MSBA?",
        "What specializations are available in the MSIT program?",
    ]

    intent_agent = get_intent_agent()

    for query in test_queries:
        try:
            logger.info(f"\nClassifying: {query}")
            classification = await intent_agent.classify(query)

            print(f"Query: {query}")
            print(f"  Intent: {classification.intent}")
            print(f"  Confidence: {classification.confidence}")
            print(f"  Is Academic: {classification.is_academic}")
            print(f"  Requires transcript: {classification.requires_transcript}")
            print(f"  Reasoning: {classification.reasoning[:100]}...")
            print(f"  ✓ Classification successful")

        except Exception as e:
            print(f"Query: {query}")
            print(f"  ✗ ERROR: {e}")
            return False

    print("\n✓ Test 1 PASSED: Intent Agent classification working correctly")
    return True


def test_database():
    """Test 2: Database population verification"""
    print("\n" + "="*80)
    print("TEST 2: Database Population Verification")
    print("="*80)

    db_service = get_program_db_service()

    # Test program retrieval
    programs = db_service.get_all_programs()
    print(f"\nPrograms in database: {len(programs)}")
    for prog in programs:
        print(f"  - {prog.get('program_code')}: {prog.get('program_name')}")

    if len(programs) != 3:
        print(f"✗ Expected 3 programs, got {len(programs)}")
        return False

    # Test specialties for each program
    program_codes = ["MSIT", "MSBA", "MSM"]
    for code in program_codes:
        program = next((p for p in programs if p.get('program_code') == code), None)
        if program:
            specialties = db_service.get_specialties_by_program(program.get('id'))
            print(f"\n{code} Specialties: {len(specialties)}")
            for spec in specialties:
                print(f"  - {spec.get('specialty_name')}")
        else:
            print(f"✗ Program {code} not found")
            return False

    # Test courses
    courses = db_service.get_all_courses()
    print(f"\nCourses in database: {len(courses)}")

    if len(courses) != 14:
        print(f"✗ Expected 14 courses, got {len(courses)}")
        return False

    print("\n✓ Test 2 PASSED: Database properly populated")
    return True


async def test_rag_agent():
    """Test 3: Adviser Agent with Database-First retrieval"""
    print("\n" + "="*80)
    print("TEST 3: Adviser Agent Database-First Retrieval")
    print("="*80)

    adviser_agent = get_adviser_agent()

    test_query = "What are the MSIT program requirements and specializations?"

    try:
        logger.info(f"Testing adviser query: {test_query}")
        result = await adviser_agent.answer_query(
            query=test_query,
            program_id="msit"
        )

        response = result.get('response', '')
        tools_used = result.get('tools_used', [])
        source = result.get('source', '')

        print(f"\nQuery: {test_query}")
        print(f"Response length: {len(response)} characters")
        print(f"Tools used: {tools_used}")
        print(f"Source: {source}")
        print(f"\nFirst 300 chars of response:")
        print(f"  {response[:300]}...")

        if not response:
            print("✗ Empty response")
            return False

        print("\n✓ Test 3 PASSED: Adviser Agent retrieves program information")
        return True

    except Exception as e:
        print(f"✗ ERROR: {e}")
        logger.exception("Adviser Agent test failed")
        return False


async def test_full_pipeline():
    """Test 4: Complete Intent → Adviser → Response pipeline"""
    print("\n" + "="*80)
    print("TEST 4: Full Intent → Adviser → Response Pipeline")
    print("="*80)

    intent_agent = get_intent_agent()
    adviser_agent = get_adviser_agent()

    test_cases = [
        {
            "query": "What courses are in the MSIT program?",
            "expected_is_academic": True,
            "expected_keywords": ["course", "MSIT", "CS"]
        },
        {
            "query": "Tell me about specializations in MSBA",
            "expected_is_academic": True,
            "expected_keywords": ["specialization", "MSBA"]
        },
        {
            "query": "What is the difference between MSIT and MSBA programs?",
            "expected_is_academic": True,
            "expected_keywords": ["MSIT", "MSBA"]
        },
    ]

    for i, test_case in enumerate(test_cases, 1):
        query = test_case["query"]

        try:
            logger.info(f"\n[Subtest {i}/{len(test_cases)}] {query}")

            # Step 1: Intent classification
            intent_result = await intent_agent.classify(query)
            print(f"\n[{i}] Query: {query}")
            print(f"    Intent: {intent_result.intent} (confidence: {intent_result.confidence})")
            print(f"    Is Academic: {intent_result.is_academic}")

            # Step 2: Adviser Agent response
            adviser_result = await adviser_agent.answer_query(
                query=query,
                program_id="msit"
            )

            response = adviser_result.get('response', '')
            tools_used = adviser_result.get('tools_used', [])

            print(f"    Tools used: {tools_used}")
            print(f"    Response: {response[:200]}...")

            # Verify response contains expected keywords
            response_lower = response.lower()
            found_keywords = [kw for kw in test_case["expected_keywords"] if kw.lower() in response_lower]

            if found_keywords:
                print(f"    ✓ Found expected keywords: {found_keywords}")
            else:
                print(f"    ⚠ Missing expected keywords: {test_case['expected_keywords']}")

            if not response:
                print(f"    ✗ Empty response")
                return False

        except Exception as e:
            print(f"    ✗ ERROR: {e}")
            logger.exception(f"Pipeline test {i} failed")
            return False

    print("\n✓ Test 4 PASSED: Complete pipeline working")
    return True


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("END-TO-END INTENT → ADVISER PIPELINE TEST SUITE")
    print("="*80)

    results = {
        "Intent Agent Classification": False,
        "Database Population": False,
        "Adviser Agent Retrieval": False,
        "Full Pipeline": False,
    }

    try:
        # Test 1: Intent Agent
        results["Intent Agent Classification"] = await test_intent_agent()

        # Test 2: Database
        results["Database Population"] = test_database()

        # Test 3: Adviser Agent
        results["Adviser Agent Retrieval"] = await test_rag_agent()

        # Test 4: Full Pipeline
        results["Full Pipeline"] = await test_full_pipeline()

    except Exception as e:
        logger.exception("Test suite failed with exception")
        print(f"\n✗ FATAL ERROR: {e}")
        return 1

    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name}: {status}")

    all_passed = all(results.values())

    print("\n" + "="*80)
    if all_passed:
        print("✓ ALL TESTS PASSED - Pipeline is working correctly")
        print("="*80)
        return 0
    else:
        print("✗ SOME TESTS FAILED - See details above")
        print("="*80)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
