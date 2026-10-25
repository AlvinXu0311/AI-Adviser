"""
PDF Vector Search Service - RAG search from academic PDF documents.

This service provides read-only semantic search across PDF documents:
- Bus-school courses.pdf
- Masters from Graduate Bus School.pdf
- Mathematical Science Courses.pdf
- computer science Courses.pdf

Uses PyMuPDF for text extraction, text chunking, and ChromaDB for vector storage.

Serving processes never write the index. Indexes are built offline into a new versioned
directory and activated atomically (see vector_index.py); every serving process notices the
switch within RELOAD_CHECK_SECONDS and moves to the new version, so retrieval keeps working
throughout a rebuild.
"""

import json
import os
import re
import logging
import threading
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

import chromadb
from dotenv import load_dotenv

# Load environment variables from backend/.env
BACKEND_DIR = Path(__file__).parent.parent.parent
ENV_PATH = BACKEND_DIR / ".env"
load_dotenv(ENV_PATH)

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # /app
PDF_SOURCE_DIR = os.path.join(BASE_DIR, "database", "database_project")
# Index written before versioned builds existed; used read-only until a version is activated
LEGACY_CHROMA_PATH = os.path.join(BASE_DIR, "database", "vector_db_pdf")
CHROMA_PATH = LEGACY_CHROMA_PATH  # kept for callers that print it
INDEX_ROOT = os.path.join(BASE_DIR, "database", "vector_index")
COLLECTION_NAME = "pdf_documents"
RELOAD_CHECK_SECONDS = float(os.getenv("VECTOR_INDEX_RELOAD_SECONDS", "5"))

# PDF files to index
PDF_FILES = [
    "Bus-school courses.pdf",
    "Masters from Graduate Bus School.pdf",
    "Mathematical Science Courses.pdf",
    "computer science Courses.pdf",
]

# Google API Key from .env
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Embedding provider: 'google' or 'local' (sentence-transformers)
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "google" if GOOGLE_API_KEY else "local").lower()
# Model for new builds; an index is always queried with the model recorded in its manifest.
# (models/embedding-001 was retired by Google, which silently broke the legacy index.)
GOOGLE_EMBEDDING_MODEL = os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-001")


class _PdfPipeline:
    """PDF text extraction, course-aware chunking and embeddings (shared by serving and the index builder)."""

    def _init_embeddings(self, provider: str = EMBEDDING_PROVIDER, allow_fallback: bool = True,
                         model: Optional[str] = None):
        """
        Initialize the embedding model. Serving passes the provider and model the index was built
        with and allow_fallback=False: query vectors from a different model would silently return garbage.
        """
        if provider == "google" and GOOGLE_API_KEY:
            try:
                from langchain_google_genai import GoogleGenerativeAIEmbeddings
                model = model or GOOGLE_EMBEDDING_MODEL
                self.embeddings = GoogleGenerativeAIEmbeddings(
                    model=model,
                    google_api_key=GOOGLE_API_KEY,
                    task_type="retrieval_query"
                )
                # Test embedding to verify API works
                test_result = self.embeddings.embed_query("test")
                if test_result and len(test_result) > 0:
                    self.embedding_type = "google"
                    self.embedding_model = model
                    self.embedding_dims = len(test_result)
                    logger.info(f"Google Embeddings {model} initialized ({len(test_result)} dimensions)")
                    return
            except Exception as e:
                logger.warning(f"Google Embeddings failed: {e}")
                logger.info("Falling back to local embeddings...")
        else:
            if not GOOGLE_API_KEY:
                logger.info("No GOOGLE_API_KEY found, using local embeddings")
        
        if provider == "google" and not allow_fallback:
            raise RuntimeError(f"Index was built with Google embeddings ({model}) but they are unavailable")
        # Fallback to local
        self._init_local_embeddings()

    def _init_local_embeddings(self):
        """Initialize local sentence-transformers embeddings"""
        try:
            from sentence_transformers import SentenceTransformer
            self.local_model = SentenceTransformer('all-MiniLM-L6-v2')
            self.embedding_type = "local"
            self.embedding_model = "all-MiniLM-L6-v2"
            self.embedding_dims = self.local_model.get_sentence_embedding_dimension()
            logger.info("Local Sentence Transformers initialized (all-MiniLM-L6-v2)")
        except Exception as e:
            logger.error(f"Failed to initialize local embeddings: {e}")
            raise

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts"""
        try:
            if self.embedding_type == "google":
                return self.embeddings.embed_documents(texts)
            else:
                # Local sentence-transformers
                return self.local_model.encode(texts).tolist()
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            raise

    def _embed_query(self, query: str) -> List[float]:
        """Generate embedding for a single query"""
        try:
            if self.embedding_type == "google":
                return self.embeddings.embed_query(query)
            else:
                return self.local_model.encode(query).tolist()
        except Exception as e:
            logger.error(f"Error generating query embedding: {e}")
            raise

    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from a PDF file using PyMuPDF"""
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(pdf_path)
            text_parts = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                if text.strip():
                    text_parts.append(f"[Page {page_num + 1}]\n{text}")
            
            doc.close()
            
            full_text = "\n\n".join(text_parts)
            logger.info(f"Extracted {len(full_text)} chars from {os.path.basename(pdf_path)}")
            return full_text
            
        except Exception as e:
            logger.error(f"Error extracting text from {pdf_path}: {e}")
            return ""

    def _chunk_text(self, text: str, source_file: str, chunk_size: int = 1500, overlap: int = 200) -> List[Dict[str, Any]]:
        """
        Split text into semantic chunks optimized for course catalogs.
        
        Strategy:
        1. First, try to split by COURSE BOUNDARIES (course code patterns)
        2. For non-course content (like program descriptions), use paragraph-based chunking
        3. Each chunk contains complete course info (code, title, description, credits)
        
        Args:
            text: Full text to chunk
            source_file: Name of source PDF file
            chunk_size: Target size of each chunk (for non-course content)
            overlap: Number of characters to overlap between chunks
            
        Returns:
            List of chunk dictionaries with text and metadata
        """
        chunks = []
        chunk_id = 0
        
        # Clean text
        text = re.sub(r'\n{3,}', '\n\n', text)  # Reduce multiple newlines
        text = re.sub(r' {2,}', ' ', text)  # Reduce multiple spaces
        
        # Course pattern: matches "CS 534", "MIS 520", "DS/ECE 577", "ECE 578/CS 578"
        # Captures cross-listed courses like "DS/ECE 577" or "ECE 578/CS 578"
        course_pattern = r'(?:^|\n)([A-Z]{2,4}(?:\s*/\s*[A-Z]{2,4})?\s+\d{3,4}(?:\s*/\s*[A-Z]{2,4}\s+\d{3,4})?)\s*:\s*([^\n]+)'
        
        # Find all course matches
        course_matches = list(re.finditer(course_pattern, text, re.MULTILINE))
        
        if course_matches:
            logger.info(f"Found {len(course_matches)} courses in {source_file}")
            
            # Extract content before first course (program info)
            first_course_start = course_matches[0].start()
            if first_course_start > 100:  # Only if there's substantial content
                preamble = text[:first_course_start].strip()
                if preamble:
                    chunks.extend(self._chunk_non_course_content(
                        preamble, source_file, chunk_id, chunk_size, overlap
                    ))
                    chunk_id = len(chunks)
            
            # Process each course
            for i, match in enumerate(course_matches):
                course_code = match.group(1).strip()
                course_title = match.group(2).strip()
                
                # Find the end of this course's content
                # (either next course start or end of text)
                start = match.start()
                if i + 1 < len(course_matches):
                    end = course_matches[i + 1].start()
                else:
                    end = len(text)
                
                course_content = text[start:end].strip()
                
                # Clean up: remove page markers that aren't relevant
                course_content = re.sub(r'\n\d+\nWPI \d{4}-\d{2} Catalog', '', course_content)
                
                # Create chunk for this course
                chunks.append({
                    "id": f"{source_file}_{chunk_id}",
                    "text": course_content,
                    "source": source_file,
                    "chunk_index": chunk_id,
                    "course_code": course_code,
                    "course_title": course_title,
                    "chunk_type": "course"
                })
                chunk_id += 1
                
                # If course content is very long, also create sub-chunks
                if len(course_content) > chunk_size * 2:
                    # Split long course descriptions into additional overlapping chunks
                    sub_chunks = self._create_overlapping_chunks(
                        course_content, source_file, chunk_id, chunk_size, overlap,
                        extra_metadata={"course_code": course_code, "course_title": course_title}
                    )
                    chunks.extend(sub_chunks)
                    chunk_id += len(sub_chunks)
        else:
            # No course patterns found - use paragraph-based chunking
            logger.info(f"No course patterns in {source_file}, using paragraph chunking")
            chunks = self._chunk_non_course_content(text, source_file, 0, chunk_size, overlap)
        
        logger.info(f"Created {len(chunks)} chunks from {source_file}")
        return chunks

    def _chunk_non_course_content(self, text: str, source_file: str, start_id: int, 
                                   chunk_size: int, overlap: int) -> List[Dict[str, Any]]:
        """Chunk non-course content (like program descriptions) using paragraphs."""
        chunks = []
        chunk_id = start_id
        
        paragraphs = text.split('\n\n')
        current_chunk = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                chunks.append({
                    "id": f"{source_file}_{chunk_id}",
                    "text": current_chunk.strip(),
                    "source": source_file,
                    "chunk_index": chunk_id,
                    "chunk_type": "program_info"
                })
                chunk_id += 1
                
                # Keep overlap
                if len(current_chunk) > overlap:
                    current_chunk = current_chunk[-overlap:] + "\n\n" + para
                else:
                    current_chunk = para
            else:
                current_chunk = current_chunk + "\n\n" + para if current_chunk else para
        
        if current_chunk.strip():
            chunks.append({
                "id": f"{source_file}_{chunk_id}",
                "text": current_chunk.strip(),
                "source": source_file,
                "chunk_index": chunk_id,
                "chunk_type": "program_info"
            })
        
        return chunks

    def _create_overlapping_chunks(self, text: str, source_file: str, start_id: int,
                                    chunk_size: int, overlap: int, 
                                    extra_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Create overlapping chunks for very long content."""
        chunks = []
        chunk_id = start_id
        
        # Simple sliding window
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end]
            
            # Try to break at sentence boundary
            if end < len(text):
                last_period = chunk_text.rfind('.')
                if last_period > chunk_size * 0.7:  # At least 70% of chunk
                    chunk_text = chunk_text[:last_period + 1]
                    end = start + last_period + 1
            
            chunk_data = {
                "id": f"{source_file}_{chunk_id}_sub",
                "text": chunk_text.strip(),
                "source": source_file,
                "chunk_index": chunk_id,
                "chunk_type": "sub_chunk"
            }
            if extra_metadata:
                chunk_data.update(extra_metadata)
            
            chunks.append(chunk_data)
            chunk_id += 1
            
            # Move forward with overlap
            start = end - overlap
            if start >= len(text) - overlap:
                break
        
        return chunks


class PDFVectorService(_PdfPipeline):
    """
    Read-only vector search over the active index version.

    Extracts nothing and writes nothing: it opens whatever version CURRENT points to (or the
    legacy index), and re-opens when CURRENT changes.
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if PDFVectorService._initialized:
            return
        self._lock = threading.Lock()
        self._last_check = 0.0
        self.version: Optional[str] = None
        self.index_path: Optional[str] = None
        self.manifest: Dict[str, Any] = {}
        self.collection = None
        self.embedding_type = "none"
        self._maybe_reload(force=True)
        PDFVectorService._initialized = True
        logger.info("PDFVectorService initialized (version=%s)", self.version)

    def _maybe_reload(self, force: bool = False) -> None:
        """Switch to the active index version if CURRENT changed (checked at most every few seconds)."""
        now = time.monotonic()
        if not force and now - self._last_check < RELOAD_CHECK_SECONDS:
            return
        with self._lock:
            if not force and now - self._last_check < RELOAD_CHECK_SECONDS:
                return
            self._last_check = now
            from .vector_index import active_index
            version, path, manifest = active_index()
            if version == self.version and self.collection is not None:
                return
            if path is None:
                logger.error("No vector index found; build one with: python -m app.services.vector_index build")
                return
            try:
                self._open(version, path, manifest)
            except Exception:
                # Keep serving the version we already have rather than going dark
                logger.exception("Could not open vector index %s; staying on %s", version, self.version)

    def _open(self, version: str, path: str, manifest: Dict[str, Any]) -> None:
        provider, model = manifest.get("embedding_type"), manifest.get("embedding_model")
        if (provider, model) != (getattr(self, "embedding_type", None), getattr(self, "embedding_model", None)):
            if provider:
                self._init_embeddings(provider, allow_fallback=False, model=model)
            else:
                self._init_embeddings()  # legacy index without a manifest: previous behaviour
        client = chromadb.PersistentClient(path=path)
        collection = client.get_collection(COLLECTION_NAME)
        # Refuse an index whose vectors don't match the query model (the legacy index silently
        # broke this way when its embedding model was retired)
        sample = collection.peek(1).get("embeddings")
        if sample is not None and len(sample) and len(sample[0]) != self.embedding_dims:
            raise RuntimeError(f"Index {version} has {len(sample[0])}-dim vectors but the query model "
                               f"{self.embedding_model} produces {self.embedding_dims}; rebuild the index")
        # Assign together so a concurrent search never sees a half-switched state
        self.chroma_client, self.collection = client, collection
        self.version, self.index_path, self.manifest = version, path, manifest
        logger.info("Serving vector index %s (%d chunks, %s embeddings)", version, collection.count(),
                    self.embedding_type)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search PDF content using semantic similarity with course-aware ranking.
        
        Strategy:
        1. First, check if query contains a course code (e.g., "ECE 577", "MIS 520")
        2. If yes, prioritize chunks that have matching course_code in metadata
        3. Use semantic similarity as secondary ranking
        
        Args:
            query: Natural language search query
            top_k: Number of results to return
            
        Returns:
            List of matching chunks with scores
        """
        self._maybe_reload()
        if self.collection is None or self.collection.count() == 0:
            logger.warning("PDF index is empty or not built")
            return []
        
        # Extract course code pattern from query
        course_code_match = re.search(r'([A-Z]{2,4})\s*/?([A-Z]{2,4})?\s*(\d{3,4})', query.upper())
        extracted_code = None
        extracted_number = None
        
        if course_code_match:
            dept1 = course_code_match.group(1)
            extracted_number = course_code_match.group(3)
            extracted_code = f"{dept1} {extracted_number}"
            logger.info(f"Extracted course code from query: {extracted_code}")
        
        # Get more results than needed for re-ranking
        fetch_k = min(top_k * 3, self.collection.count())
        query_embedding = self._embed_query(query)
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=fetch_k,
            include=["documents", "metadatas", "distances"]
        )
        
        formatted_results = []
        
        if results['ids'] and results['ids'][0]:
            for i, chunk_id in enumerate(results['ids'][0]):
                metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                document = results['documents'][0][i] if results['documents'] else ""
                distance = results['distances'][0][i] if results['distances'] else 1.0
                
                # Convert distance to similarity score
                base_score = 1 / (1 + distance)
                
                # Boost score for exact course code matches
                boost = 0.0
                chunk_course_code = str(metadata.get("course_code", ""))
                
                if extracted_code and chunk_course_code and extracted_number:
                    # Check for exact match or cross-listed match
                    if extracted_number in chunk_course_code:
                        boost = 0.3  # Significant boost for course number match
                        logger.debug(f"Boosting chunk {chunk_id}: course {chunk_course_code} matches {extracted_number}")
                    if extracted_code in chunk_course_code.upper().replace("/", " "):
                        boost = 0.5  # Strong boost for exact code match
                
                # Also check document text for course code (for chunks without metadata)
                if extracted_code and boost == 0 and extracted_number:
                    # Look for pattern like "DS/ECE 577" or "ECE 577"
                    if re.search(rf'\b{extracted_number}\b', document):
                        boost = 0.15  # Smaller boost for text match
                
                final_score = min(1.0, base_score + boost)
                
                formatted_results.append({
                    "chunk_id": chunk_id,
                    "text": document,
                    "source": metadata.get("source", "Unknown"),
                    "chunk_index": metadata.get("chunk_index", 0),
                    "course_code": chunk_course_code,
                    "course_title": metadata.get("course_title", ""),
                    "chunk_type": metadata.get("chunk_type", ""),
                    "score": final_score,
                    "base_score": base_score,
                    "boost": boost,
                })
        
        # Sort by final score (descending)
        formatted_results.sort(key=lambda x: x['score'], reverse=True)
        
        return formatted_results[:top_k]

    def get_context_for_query(self, query: str, max_context_length: int = 4000) -> str:
        """
        Get relevant context from PDFs for a query.
        
        This is useful for RAG - returns concatenated relevant chunks
        that can be used as context for LLM.
        
        Args:
            query: User query
            max_context_length: Maximum total context length
            
        Returns:
            Concatenated relevant context
        """
        results = self.search(query, top_k=8)
        
        if not results:
            return ""
        
        context_parts = []
        total_length = 0
        
        for result in results:
            chunk_text = result['text']
            source = result['source'].replace('.pdf', '')
            
            # Add source attribution
            formatted = f"[Source: {source}]\n{chunk_text}\n"
            
            if total_length + len(formatted) > max_context_length:
                # Truncate to fit
                remaining = max_context_length - total_length
                if remaining > 100:
                    formatted = formatted[:remaining] + "..."
                    context_parts.append(formatted)
                break
            
            context_parts.append(formatted)
            total_length += len(formatted)
        
        return "\n---\n".join(context_parts)

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the PDF index"""
        self._maybe_reload()
        return {
            "total_chunks": self.collection.count() if self.collection is not None else 0,
            "pdf_files": PDF_FILES,
            "embedding_type": self.embedding_type,
            "embedding_model": getattr(self, "embedding_model", None),
            "pdf_source_dir": PDF_SOURCE_DIR,
            "vector_db_path": self.index_path,
            "index_version": self.version,
            "index_built_at": self.manifest.get("built_at"),
        }



# Singleton instance
_pdf_service_instance: Optional[PDFVectorService] = None


def get_pdf_vector_service() -> PDFVectorService:
    """Get singleton instance of PDFVectorService"""
    global _pdf_service_instance
    if _pdf_service_instance is None:
        _pdf_service_instance = PDFVectorService()
    return _pdf_service_instance
