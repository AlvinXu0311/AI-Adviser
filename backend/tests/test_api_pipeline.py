#!/usr/bin/env python3
"""
Integration test for Intent → RAG → Response pipeline via HTTP API.
Tests the complete flow through the /api/chat endpoint.
"""
import asyncio
import aiohttp
import json
import sys
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000"


async def test_chat_api(query: str, session_id: str = None):
    """Test chat API endpoint"""
    if not session_id:
        session_id = f"test-session-{int(time.time())}"

    url = f"{API_BASE_URL}/api/chat"
    payload = {
        "message": query,
        "session_id": session_id
    }

    logger.info(f"Sending query: {query}")
    logger.info(f"Session ID: {session_id}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"API returned {resp.status}: {error_text}")
                    return None

                # Process streaming response
                full_response = ""
                events_received = []

                async for line in resp.content:
                    if not line:
                        continue

                    line_str = line.decode('utf-8').strip()
                    if not line_str:
                        continue

                    if line_str.startswith('data:'):
                        payload_str = line_str[5:].strip()
                        try:
                            event = json.loads(payload_str)
                            events_received.append(event)
                            event_type = event.get('type', 'unknown')
                            logger.debug(f"Received event: {event_type}")

                            if event_type in ['token', 'final']:
                                content = event.get('data', {}).get('content', '')
                                full_response += content

                        except json.JSONDecodeError as e:
                            logger.debug(f"Failed to parse event: {e}")

                return {
                    "query": query,
                    "response": full_response,
                    "events_count": len(events_received),
                    "session_id": session_id
                }

    except asyncio.TimeoutError:
        logger.error("Request timed out")
        return None
    except Exception as e:
        logger.error(f"Request failed: {e}")
        return None


async def main():
    """Run pipeline tests via API"""
    print("\n" + "="*80)
    print("API PIPELINE INTEGRATION TEST")
    print("="*80)

    test_queries = [
        "What are the MSIT program requirements?",
        "Tell me about MSBA courses and specializations",
        "What specializations are available in MSM?",
    ]

    results = []

    # Check if server is running
    logger.info(f"Checking if server is running at {API_BASE_URL}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE_URL}/", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 404:  # 404 is expected since there's no root endpoint
                    logger.info("✓ Server is reachable")
    except Exception as e:
        logger.error(f"✗ Cannot reach server at {API_BASE_URL}: {e}")
        print("\n✗ FATAL: Server is not running. Start backend with:")
        print("   cd backend && source venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
        return 1

    # Run tests
    print("\n" + "="*80)
    print("TEST QUERIES")
    print("="*80)

    for i, query in enumerate(test_queries, 1):
        print(f"\n[Test {i}/{len(test_queries)}]")
        result = await test_chat_api(query)

        if result:
            print(f"Query: {result['query']}")
            print(f"Response length: {len(result['response'])} characters")
            print(f"Events received: {result['events_count']}")
            print(f"Response preview: {result['response'][:200]}...")
            results.append(True)

            if not result['response']:
                print("⚠ WARNING: Empty response")
                results[-1] = False
        else:
            print(f"Query: {query}")
            print("✗ FAILED")
            results.append(False)

        # Add delay between requests
        await asyncio.sleep(1)

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = sum(1 for r in results if r)
    total = len(results)

    for i, (query, passed_flag) in enumerate(zip(test_queries, results), 1):
        status = "✓ PASS" if passed_flag else "✗ FAIL"
        print(f"{i}. {status}: {query[:60]}...")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✓ ALL TESTS PASSED - Pipeline is working correctly")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
