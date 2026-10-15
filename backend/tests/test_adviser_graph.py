"""
Offline tests for the LangGraph adviser agent.
A scripted chat model stands in for Gemini; the ToolNode runs the real tools.
"""
from typing import Any, List

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agents import adviser_agent as adviser_module
from app.agents.adviser_agent import AdviserAgent, FORCE_ANSWER_NOTE, _history_to_messages


class ScriptedChatModel(BaseChatModel):
    """Returns the scripted replies in order and records every prompt it receives."""

    replies: List[AIMessage]
    calls: List[List[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.calls.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=self.replies[len(self.calls) - 1])])


def _tool_call_reply(*calls: dict, thinking: str = "") -> AIMessage:
    content = [{"type": "thinking", "thinking": thinking}] if thinking else ""
    return AIMessage(content=content, tool_calls=list(calls))


def _make_agent(monkeypatch, replies: List[AIMessage]) -> tuple[AdviserAgent, ScriptedChatModel]:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    agent = AdviserAgent()
    model = ScriptedChatModel(replies=replies, calls=[])
    agent.llm = model
    agent.graph = agent._build_graph()
    return agent, model


async def _run(agent: AdviserAgent, query: str) -> tuple[dict, list]:
    events = []

    async def sink(event):
        events.append(event)

    result = await agent.answer_query(query, on_event=sink)
    return result, events


async def test_tool_round_then_answer_streams_events(monkeypatch):
    agent, model = _make_agent(monkeypatch, [
        _tool_call_reply(
            {"name": "student_context", "args": {"info_type": "gpa"}, "id": "call_1"},
            {"name": "business_school_database", "args": {"query": "all"}, "id": "call_2"},
            thinking="I should check the transcript and the program list.",
        ),
        AIMessage(content="According to the database, here is the overview."),
    ])

    result, events = await _run(agent, "Tell me about programs")

    types = [e["type"] for e in events]
    assert types.count("agent_action") == 2
    assert types.count("tool_start") == 2
    assert types.count("tool_end") == 2
    assert types[-1] == "agent_finish"

    actions = [e for e in events if e["type"] == "agent_action"]
    assert actions[0]["thought"] == "I should check the transcript and the program list."
    assert actions[1]["thought"] == ""

    start_ids = {e["id"] for e in events if e["type"] == "tool_start"}
    end_ids = {e["id"] for e in events if e["type"] == "tool_end"}
    assert start_ids == end_ids == {"call_1", "call_2"}

    assert result["response"] == "According to the database, here is the overview."
    assert result["tools_used"] == ["student_context", "business_school_database"]
    assert len(model.calls) == 2


async def test_tool_budget_forces_final_answer(monkeypatch):
    monkeypatch.setattr(adviser_module, "MAX_TOOL_ROUNDS", 1)
    agent, model = _make_agent(monkeypatch, [
        _tool_call_reply({"name": "student_context", "args": {"info_type": "all"}, "id": "call_1"}),
        AIMessage(content="Here is what I could find."),
    ])

    result, _ = await _run(agent, "What is my GPA?")

    assert result["response"].startswith("Here is what I could find.")
    last_prompt = model.calls[-1]
    assert isinstance(last_prompt[-1], HumanMessage)
    assert last_prompt[-1].content == FORCE_ANSWER_NOTE


def test_history_to_messages_drops_current_query():
    history = [
        {"role": "user", "content": "Tell me about MSIT"},
        {"role": "assistant", "content": "MSIT is ..."},
        {"role": "user", "content": "And MSBA?"},
    ]

    messages = _history_to_messages(history, "And MSBA?")

    assert [type(m) for m in messages] == [HumanMessage, AIMessage]
    assert messages[0].content == "Tell me about MSIT"


async def test_compacted_summary_reaches_system_prompt(monkeypatch):
    agent, model = _make_agent(monkeypatch, [AIMessage(content="You are in MSIT.")])

    await agent.answer_query("Which program am I in?", conversation_summary="- Student is in MSIT")

    system_prompt = model.calls[0][0].content
    assert "EARLIER CONVERSATION" in system_prompt
    assert "- Student is in MSIT" in system_prompt
