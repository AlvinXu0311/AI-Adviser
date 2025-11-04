"""
RAG (Retrieval-Augmented Generation) Agent for knowledge base retrieval.
Focuses exclusively on retrieving and formatting program information from the knowledge base.
Does not handle conversational logic - that's the Chat Agent's responsibility.
"""
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class RAGAgent:
    """
    Dedicated RAG agent for knowledge base retrieval.
    Retrieves program information, courses, specializations, and FAQs.
    """

    def __init__(self):
        """Initialize RAG agent with knowledge base service"""
        from ..services.rag_service import get_rag_service
        self.rag_service = get_rag_service()
        logger.info("RAG Agent initialized")

    async def retrieve_for_query(
        self,
        query: str,
        program_id: str = "msit",
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Retrieve relevant information from knowledge base for a query.

        Args:
            query: User's question
            program_id: Program to search in (msit, msba, msm)
            top_k: Number of top results to return

        Returns:
            Dict with retrieved context and metadata
        """
        try:
            logger.info(f"RAG Agent retrieving for query: '{query[:50]}...'")

            # Get context from RAG service
            context = self.rag_service.get_context_for_query(
                query,
                program_id=program_id,
                top_k=top_k,
                use_bm25=True
            )

            if context:
                logger.info(f"RAG retrieved {len(context)} chars of context")
                return {
                    "status": "success",
                    "context": context,
                    "program_id": program_id,
                    "query": query,
                    "source": "knowledge_base"
                }
            else:
                logger.warning("RAG returned empty context")
                return {
                    "status": "no_results",
                    "context": None,
                    "program_id": program_id,
                    "query": query,
                    "source": "knowledge_base"
                }

        except Exception as e:
            logger.error(f"Error in RAG retrieval: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "context": None,
                "error": str(e),
                "source": "knowledge_base"
            }

    async def get_program_overview(self, program_id: str = "msit") -> Dict[str, Any]:
        """Get full program overview and structure."""
        try:
            program = self.rag_service.retrieve_program_info(program_id)
            if program:
                return {
                    "status": "success",
                    "program": program,
                    "source": "knowledge_base"
                }
            else:
                return {
                    "status": "not_found",
                    "program": None,
                    "source": "knowledge_base"
                }
        except Exception as e:
            logger.error(f"Error retrieving program overview: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "source": "knowledge_base"
            }

    async def get_course_details(self, course_code: str, program_id: str = "msit") -> Dict[str, Any]:
        """Get detailed information about a specific course."""
        try:
            course = self.rag_service.get_course_info(course_code, program_id)
            if course:
                return {
                    "status": "success",
                    "course": course,
                    "source": "knowledge_base"
                }
            else:
                return {
                    "status": "not_found",
                    "course": None,
                    "source": "knowledge_base"
                }
        except Exception as e:
            logger.error(f"Error retrieving course details: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "source": "knowledge_base"
            }

    async def get_specializations(self, program_id: str = "msit") -> Dict[str, Any]:
        """Get all available specializations for a program."""
        try:
            specs = self.rag_service.get_specializations(program_id)
            if specs:
                return {
                    "status": "success",
                    "specializations": specs,
                    "count": len(specs),
                    "source": "knowledge_base"
                }
            else:
                return {
                    "status": "not_found",
                    "specializations": [],
                    "count": 0,
                    "source": "knowledge_base"
                }
        except Exception as e:
            logger.error(f"Error retrieving specializations: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "source": "knowledge_base"
            }


# Singleton instance
_rag_agent = None


def get_rag_agent() -> RAGAgent:
    """Get or create the RAG agent"""
    global _rag_agent
    if _rag_agent is None:
        _rag_agent = RAGAgent()
    return _rag_agent
