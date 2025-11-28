import asyncio
import time
import pytest

from app.agents.intent_agent import IntentAgent


class _HangingChain:
    def invoke(self, _inputs):
        time.sleep(10)  # Simulate hanging

    async def ainvoke(self, _inputs):
        await asyncio.sleep(10)


@pytest.mark.asyncio
async def test_intent_agent_times_out(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    agent = IntentAgent()
    agent.chain = _HangingChain()
    agent.timeout = 0.05

    with pytest.raises(TimeoutError):
        await agent.classify("test message")
