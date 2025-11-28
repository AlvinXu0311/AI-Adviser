"""
Agents module for LangChain-based academic adviser system.
Implements ReAct (Reasoning and Acting) pattern with Database-First architecture:
- AdviserAgent: Conversational advising with tool use (database, student_context, assess_complexity)
- IntentAgent: LLM-powered free-form intent classification
"""

from .adviser_agent import AdviserAgent, get_adviser_agent
from .intent_agent import IntentAgent, get_intent_agent
from .tools import get_all_tools

__all__ = [
    "AdviserAgent",
    "get_adviser_agent",
    "IntentAgent",
    "get_intent_agent",
    "get_all_tools"
]
