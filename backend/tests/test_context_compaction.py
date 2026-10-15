"""
Tests for Redis chat-context compaction, against fakeredis and a scripted summarizer.
"""
import json

import fakeredis
import pytest
from langchain_core.messages import AIMessage, HumanMessage, message_to_dict

from app.services import context_compaction as compaction
from app.services.context_compaction import (
    ContextCompactor,
    message_key,
    split_for_compaction,
    summary_key,
    summary_preamble,
)


class FakeSummarizer:
    def __init__(self, reply="- Student is in MSIT"):
        self.reply = reply
        self.prompts = []

    async def ainvoke(self, messages):
        self.prompts.append(messages[0].content)
        return AIMessage(content=self.reply)


def _push(redis, session_id, messages):
    # Same layout as RedisChatMessageHistory: LPUSH, newest at index 0
    for message in messages:
        redis.lpush(message_key(session_id), json.dumps(message_to_dict(message)))


def _turns(n):
    messages = []
    for i in range(n):
        messages.append(HumanMessage(content=f"question {i}"))
        messages.append(AIMessage(content=f"answer {i}"))
    return messages


@pytest.fixture
def redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture(autouse=True)
def thresholds(monkeypatch):
    monkeypatch.setattr(compaction, "TRIGGER_MESSAGES", 8)
    monkeypatch.setattr(compaction, "TRIGGER_TOKENS", 10_000)
    monkeypatch.setattr(compaction, "KEEP_RECENT", 4)


async def test_below_threshold_does_nothing(redis):
    summarizer = FakeSummarizer()
    compactor = ContextCompactor(redis, session_ttl=100, llm=summarizer)
    _push(redis, "s1", _turns(4))  # 8 messages, not over 8

    assert await compactor.maybe_compact("s1") is False
    assert summarizer.prompts == []
    assert redis.llen(message_key("s1")) == 8


async def test_compaction_folds_oldest_and_keeps_recent(redis):
    summarizer = FakeSummarizer()
    compactor = ContextCompactor(redis, session_ttl=100, llm=summarizer)
    _push(redis, "s1", _turns(5))  # 10 messages

    assert await compactor.maybe_compact("s1") is True

    remaining = [m.content for m in compactor._load_messages("s1")]
    assert remaining == ["question 3", "answer 3", "question 4", "answer 4"]
    assert redis.get(summary_key("s1")) == "- Student is in MSIT"
    assert 0 < redis.ttl(summary_key("s1")) <= 100
    assert "question 0" in summarizer.prompts[0]
    assert "question 3" not in summarizer.prompts[0]


async def test_second_compaction_merges_previous_summary(redis):
    summarizer = FakeSummarizer()
    compactor = ContextCompactor(redis, session_ttl=100, llm=summarizer)
    redis.set(summary_key("s1"), "- earlier facts")
    _push(redis, "s1", _turns(5))

    await compactor.maybe_compact("s1")

    assert "- earlier facts" in summarizer.prompts[0]


async def test_messages_added_during_summary_are_kept(redis):
    class SlowSummarizer(FakeSummarizer):
        async def ainvoke(self, messages):
            # A new turn arrives while the summary is being written
            _push(redis, "s1", [HumanMessage(content="new question")])
            return await super().ainvoke(messages)

    compactor = ContextCompactor(redis, session_ttl=100, llm=SlowSummarizer())
    _push(redis, "s1", _turns(5))

    await compactor.maybe_compact("s1")

    remaining = [m.content for m in compactor._load_messages("s1")]
    assert remaining == ["question 3", "answer 3", "question 4", "answer 4", "new question"]


async def test_lock_prevents_concurrent_compaction(redis):
    summarizer = FakeSummarizer()
    compactor = ContextCompactor(redis, session_ttl=100, llm=summarizer)
    _push(redis, "s1", _turns(5))
    redis.set("chat_compaction_lock:s1", "1")

    assert await compactor.maybe_compact("s1") is False
    assert summarizer.prompts == []


async def test_empty_summary_leaves_history_untouched(redis):
    compactor = ContextCompactor(redis, session_ttl=100, llm=FakeSummarizer(reply="  "))
    _push(redis, "s1", _turns(5))

    assert await compactor.maybe_compact("s1") is False
    assert redis.llen(message_key("s1")) == 10
    assert redis.get(summary_key("s1")) is None


def test_token_threshold_triggers(monkeypatch, redis):
    monkeypatch.setattr(compaction, "TRIGGER_TOKENS", 50)
    compactor = ContextCompactor(redis, session_ttl=100, llm=FakeSummarizer())
    long_turns = [HumanMessage(content="x" * 300), AIMessage(content="y" * 300)] * 3

    assert compactor.needs_compaction(long_turns) is True


def test_split_keeps_window_starting_on_student_turn():
    # Odd window size would start on an adviser reply; the cut moves forward one message
    messages = _turns(4)
    assert split_for_compaction(messages, keep_recent=3) == 6
    assert split_for_compaction(messages, keep_recent=4) == 4


def test_summary_preamble():
    assert summary_preamble("") == ""
    assert "- MSIT" in summary_preamble("- MSIT")
