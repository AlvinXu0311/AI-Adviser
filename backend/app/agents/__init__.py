"""
Agents module for LangChain-based academic adviser system.
Implements ReAct (Reasoning and Acting) pattern with separated concerns:
- RAG Agent: Knowledge retrieval from program database
- Chat Agent (AdviserAgent): Conversational advising with tool use
"""

from .adviser_agent import AdviserAgent, get_adviser_agent
from .rag_agent import RAGAgent, get_rag_agent
from .tools import get_all_tools

__all__ = [
    "AdviserAgent",
    "get_adviser_agent",
    "RAGAgent",
    "get_rag_agent",
    "get_all_tools"
]
