"""
Chains module for LangChain-based processing pipelines.
Implements RAG and chat chains for academic advising.
"""

from .rag_chain import RAGChain, get_rag_chain
from .chat_chain import ChatChain, get_chat_chain

__all__ = [
    "RAGChain",
    "get_rag_chain",
    "ChatChain",
    "get_chat_chain"
]
