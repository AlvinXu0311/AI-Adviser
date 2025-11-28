"""
Chains module for LangChain-based processing pipelines.
Implements chat chains for academic advising with Database-First architecture.
"""

from .chat_chain import ChatChain, get_chat_chain

__all__ = [
    "ChatChain",
    "get_chat_chain"
]
