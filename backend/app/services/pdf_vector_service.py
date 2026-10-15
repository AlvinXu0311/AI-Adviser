"""
PDF Vector Search Service - RAG search from academic PDF documents.

This service provides semantic search across PDF documents:
- Bus-school courses.pdf
- Masters from Graduate Bus School.pdf
- Mathematical Science Courses.pdf
- computer science Courses.pdf

Uses PyMuPDF for text extraction, text chunking, and ChromaDB for vector storage.
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from hashlib import md5

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
CHROMA_PATH = os.path.join(BASE_DIR, "database", "vector_db_pdf")

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


class PDFVectorService:
    """
    Vector search service for academic PDF documents.
    
    Extracts text from PDFs, chunks content, creates embeddings,
    and provides semantic search capabilities.
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
        
        logger.info(f"Initializing PDFVectorService with {EMBEDDING_PROVIDER} embeddings...")
        
        # Initialize embeddings based on provider
        self._init_embeddings()
        
        # Initialize ChromaDB with persistent storage
        os.makedirs(CHROMA_PATH, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        
        # Create collection for PDF documents
        self.collection = self._get_or_create_collection("pdf_documents")
        
        # Build index if empty or PDFs changed
        self._ensure_index()
        
        PDFVectorService._initialized = True
        logger.info("PDFVectorService initialized successfully")
    
    def _init_embeddings(self):
        """Initialize embedding model based on provider setting"""
        if EMBEDDING_PROVIDER == "google" and GOOGLE_API_KEY:
            try:
                from langchain_google_genai import GoogleGenerativeAIEmbeddings
                self.embeddings = GoogleGenerativeAIEmbeddings(
                    model="models/embedding-001",
                    google_api_key=GOOGLE_API_KEY,
                    task_type="retrieval_query"
                )
                # Test embedding to verify API works
                test_result = self.embeddings.embed_query("test")
                if test_result and len(test_result) > 0:
                    self.embedding_type = "google"
                    logger.info(f"Google Embeddings initialized successfully ({len(test_result)} dimensions)")
                    return
            except Exception as e:
                logger.warning(f"Google Embeddings failed: {e}")
                logger.info("Falling back to local embeddings...")
        else:
            if not GOOGLE_API_KEY:
                logger.info("No GOOGLE_API_KEY found, using local embeddings")
        
        # Fallback to local
        self._init_local_embeddings()
    
    def _init_local_embeddings(self):
        """Initialize local sentence-transformers embeddings"""
        try:
            from sentence_transformers import SentenceTransformer
            self.local_model = SentenceTransformer('all-MiniLM-L6-v2')
            self.embedding_type = "local"
            logger.info("Local Sentence Transformers initialized (all-MiniLM-L6-v2)")
        except Exception as e:
            logger.error(f"Failed to initialize local embeddings: {e}")
            raise
    
    def _get_or_create_collection(self, name: str):
        """Get or create a ChromaDB collection"""
        return self.chroma_client.get_or_create_collection(
            name=name,
            metadata={"description": "WPI Academic PDF Documents"}
        )
    
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
    
    def _get_pdf_hash(self) -> str:
        """Get combined hash of all PDF files to detect changes"""
        hash_parts = []
        for pdf_name in PDF_FILES:
            pdf_path = os.path.join(PDF_SOURCE_DIR, pdf_name)
            if os.path.exists(pdf_path):
                stat = os.stat(pdf_path)
                hash_parts.append(f"{pdf_name}:{stat.st_size}:{stat.st_mtime}")
        return md5("|".join(hash_parts).encode()).hexdigest()
    
    def _get_stored_hash(self) -> Optional[str]:
        """Get previously stored hash from collection metadata"""
        try:
            metadata = self.collection.metadata or {}
            return metadata.get("pdf_hash")
        except:
            return None
    
    def _update_stored_hash(self, new_hash: str):
        """Update stored hash in collection metadata"""
        try:
            self.collection.modify(metadata={"pdf_hash": new_hash})
        except Exception as e:
            logger.warning(f"Could not update hash metadata: {e}")
    
    def _ensure_index(self):
        """Build vector index if collection is empty or PDFs changed"""
        current_hash = self._get_pdf_hash()
        stored_hash = self._get_stored_hash()
        
        if self.collection.count() == 0:
            logger.info("Empty collection, building PDF index...")
            self._build_pdf_index()
            self._update_stored_hash(current_hash)
        elif current_hash != stored_hash:
            logger.info("PDF files changed, rebuilding index...")
            self.rebuild_index()
        else:
            logger.info(f"PDF index up to date with {self.collection.count()} chunks")
    
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
    
    def _build_pdf_index(self):
        """Build vector index from all PDF files"""
        logger.info("Building PDF vector index...")
        
        all_chunks = []
        
        for pdf_name in PDF_FILES:
            pdf_path = os.path.join(PDF_SOURCE_DIR, pdf_name)
            
            if not os.path.exists(pdf_path):
                logger.warning(f"PDF not found: {pdf_path}")
                continue
            
            # Extract text from PDF
            text = self._extract_text_from_pdf(pdf_path)
            
            if not text:
                logger.warning(f"No text extracted from {pdf_name}")
                continue
            
            # Chunk the text
            chunks = self._chunk_text(text, pdf_name)
            all_chunks.extend(chunks)
            logger.info(f"Created {len(chunks)} chunks from {pdf_name}")
        
        if not all_chunks:
            logger.warning("No chunks created from PDFs")
            return
        
        # Prepare data for ChromaDB
        ids = [chunk["id"] for chunk in all_chunks]
        documents = [chunk["text"] for chunk in all_chunks]
        metadatas = []
        for chunk in all_chunks:
            meta: Dict[str, Any] = {
                "source": chunk["source"],
                "chunk_index": chunk["chunk_index"],
            }
            # Add optional course metadata if present
            if "course_code" in chunk:
                meta["course_code"] = chunk["course_code"]
            if "course_title" in chunk:
                meta["course_title"] = chunk["course_title"]
            if "chunk_type" in chunk:
                meta["chunk_type"] = chunk["chunk_type"]
            metadatas.append(meta)
        
        # Generate embeddings in batches to avoid memory issues
        batch_size = 50
        all_embeddings = []
        
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            batch_embeddings = self._embed_texts(batch)
            all_embeddings.extend(batch_embeddings)
            logger.info(f"Embedded batch {i // batch_size + 1}/{(len(documents) + batch_size - 1) // batch_size}")
        
        # Add to collection
        self.collection.add(
            ids=ids,
            embeddings=all_embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        # Update hash
        self._update_stored_hash(self._get_pdf_hash())
        
        logger.info(f"Indexed {len(all_chunks)} chunks from {len(PDF_FILES)} PDFs")
    
    def rebuild_index(self):
        """Force rebuild of the PDF vector index"""
        logger.info("Rebuilding PDF index...")
        
        try:
            self.chroma_client.delete_collection("pdf_documents")
        except:
            pass
        
        self.collection = self._get_or_create_collection("pdf_documents")
        self._build_pdf_index()
    
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
        if self.collection.count() == 0:
            logger.warning("PDF index is empty")
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
        return {
            "total_chunks": self.collection.count(),
            "pdf_files": PDF_FILES,
            "embedding_type": self.embedding_type,
            "pdf_source_dir": PDF_SOURCE_DIR,
            "vector_db_path": CHROMA_PATH,
        }


# Singleton instance
_pdf_service_instance: Optional[PDFVectorService] = None


def get_pdf_vector_service() -> PDFVectorService:
    """Get singleton instance of PDFVectorService"""
    global _pdf_service_instance
    if _pdf_service_instance is None:
        _pdf_service_instance = PDFVectorService()
    return _pdf_service_instance
