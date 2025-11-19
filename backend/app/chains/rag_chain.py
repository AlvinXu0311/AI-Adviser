"""
RAG Chain using LangChain with semantic and BM25 retrieval.
Implements agentic RAG pattern with hybrid search capabilities.
"""
from typing import Optional, Dict, Any, List
from langchain.chains import RetrievalQA
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
from langchain.schema import Document
import logging
import json
from pathlib import Path
import os

logger = logging.getLogger(__name__)


class RAGChain:
    """
    Agentic RAG chain combining semantic search with BM25 retrieval.
    Optimized for academic advising with program knowledge base.
    """

    def __init__(self, knowledge_base_path: Optional[str] = None):
        """
        Initialize RAG chain with hybrid retriever.

        Args:
            knowledge_base_path: Path to knowledge base JSON file
        """
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")

        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.7,
            max_output_tokens=2048,
            google_api_key=api_key
        )

        self.knowledge_base_path = knowledge_base_path or self._get_default_kb_path()
        self.documents = []
        self.vector_store = None
        self.bm25_retriever = None
        self.ensemble_retriever = None
        self.chain = None

        self._initialize_retrieval()
        self._create_chain()

    def _get_default_kb_path(self) -> str:
        """Get default knowledge base path"""
        return str(Path(__file__).parent.parent / "knowledge_base" / "programs.json")

    def _initialize_retrieval(self):
        """Initialize hybrid retrieval with semantic and BM25"""
        try:
            logger.info("Initializing hybrid retrieval...")

            # Load documents
            self.documents = self._load_documents()
            logger.info(f"Loaded {len(self.documents)} documents")

            if not self.documents:
                logger.warning("No documents loaded for retrieval")
                return

            # Initialize BM25 retriever
            self.bm25_retriever = BM25Retriever.from_documents(self.documents)
            self.bm25_retriever.k = 5
            logger.info("BM25 retriever initialized")

            # Initialize vector store for semantic search
            try:
                from langchain_community.embeddings import HuggingFaceEmbeddings

                embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
                self.vector_store = Chroma.from_documents(
                    documents=self.documents,
                    embedding=embeddings,
                    persist_directory="/tmp/chroma_db"
                )
                logger.info("Vector store initialized with Chroma")

                # Create ensemble retriever (BM25 + semantic)
                semantic_retriever = self.vector_store.as_retriever(
                    search_kwargs={"k": 5}
                )

                self.ensemble_retriever = EnsembleRetriever(
                    retrievers=[self.bm25_retriever, semantic_retriever],
                    weights=[0.5, 0.5]
                )
                logger.info("Ensemble retriever created (BM25 50% + Semantic 50%)")
            except Exception as e:
                logger.warning(f"Vector store initialization failed, using BM25 only: {str(e)}")
                self.ensemble_retriever = self.bm25_retriever

        except Exception as e:
            logger.error(f"Error initializing retrieval: {str(e)}", exc_info=True)

    def _load_documents(self) -> List[Document]:
        """Load documents from knowledge base JSON"""
        documents = []
        try:
            with open(self.knowledge_base_path, 'r') as f:
                data = json.load(f)

            for program in data.get("programs", []):
                # Create document for program overview
                program_doc = Document(
                    page_content=f"""Program: {program['name']}
Overview: {program.get('overview', '')}
Total Credits: {program.get('total_credits')}
Duration: {program.get('duration')}""",
                    metadata={"program_id": program["id"], "type": "overview"}
                )
                documents.append(program_doc)

                # Create documents for core courses
                for course in program.get("core_courses", []):
                    course_doc = Document(
                        page_content=f"""Course: {course['name']} ({course['code']})
Credits: {course.get('credits', '')}
Description: {course.get('description', '')}
Prerequisites: {course.get('prerequisites', 'None')}""",
                        metadata={
                            "program_id": program["id"],
                            "type": "core_course",
                            "course_code": course["code"]
                        }
                    )
                    documents.append(course_doc)

                # Create documents for specializations
                for spec in program.get("specializations", []):
                    spec_doc = Document(
                        page_content=f"""Specialization: {spec['name']}
Description: {spec.get('description', '')}
Courses: {', '.join([c['code'] for c in spec.get('courses', [])])}""",
                        metadata={
                            "program_id": program["id"],
                            "type": "specialization",
                            "spec_id": spec["id"]
                        }
                    )
                    documents.append(spec_doc)

            logger.info(f"Loaded {len(documents)} documents from knowledge base")
            return documents

        except Exception as e:
            logger.error(f"Error loading documents: {str(e)}")
            return []

    def _create_chain(self):
        """Create the RAG chain with custom prompt"""
        if not self.ensemble_retriever:
            logger.warning("Ensemble retriever not available, chain creation skipped")
            return

        template = """Use the following context from the program knowledge base to answer the student's question.

Context:
{context}

Question: {question}

Guidelines:
- Answer based ONLY on the provided context
- If information is not in the context, say "I don't have that information"
- Be concise and direct
- Cite specific details from the knowledge base when relevant

Answer:"""

        prompt = PromptTemplate(
            template=template,
            input_variables=["context", "question"]
        )

        self.chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.ensemble_retriever,
            prompt=prompt,
            return_source_documents=True,
            verbose=True
        )

        logger.info("RAG chain created")

    async def query(self, question: str, program_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Query the RAG chain with optional program filtering.

        Args:
            question: Student's question
            program_id: Optional program filter (msit, msba, msm)

        Returns:
            Dict with response, sources, and metadata
        """
        try:
            if not self.chain:
                raise ValueError("RAG chain not initialized")

            logger.info(f"RAG query: {question[:50]}...")

            result = self.chain({"query": question})

            response = {
                "answer": result.get("result", ""),
                "sources": self._extract_sources(result.get("source_documents", [])),
                "confidence": self._calculate_confidence(result),
                "retrieval_method": "hybrid_rag"
            }

            logger.info(f"RAG response generated: {len(response['answer'])} chars")
            return response

        except Exception as e:
            logger.error(f"Error in RAG query: {str(e)}", exc_info=True)
            raise ValueError(f"RAG query failed: {str(e)}")

    def _extract_sources(self, source_documents: List) -> List[Dict[str, str]]:
        """Extract source information from retrieved documents"""
        sources = []
        for doc in source_documents:
            sources.append({
                "content": doc.page_content[:200],
                "metadata": doc.metadata
            })
        return sources

    def _calculate_confidence(self, result: Dict) -> float:
        """Calculate confidence score based on retrieval results"""
        sources = result.get("source_documents", [])
        if not sources:
            return 0.0
        if len(sources) >= 5:
            return 0.9
        if len(sources) >= 3:
            return 0.7
        return 0.5


# Singleton instance
_rag_chain = None


def get_rag_chain(knowledge_base_path: Optional[str] = None) -> RAGChain:
    """Get or create the RAG chain"""
    global _rag_chain
    if _rag_chain is None:
        _rag_chain = RAGChain(knowledge_base_path)
    return _rag_chain
