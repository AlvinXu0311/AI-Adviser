"""
Vector Search Service - Hybrid RAG search for academic entities.

This service provides intelligent semantic search across multiple entity types:
- Courses: Search by topic, description, instructor
- Programs: Search by program name, description, requirements
- Specialties: Search by specialty name, focus area

Combines:
1. Vector Search: Semantic similarity using Google Embeddings (primary) or local fallback
2. Keyword Matching: Exact/fuzzy matching on codes and names
3. Database Lookup: Full details from SQLite
"""

import os
import sqlite3
import logging
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

import chromadb
from dotenv import load_dotenv

# Load environment variables from backend/.env
BACKEND_DIR = Path(__file__).parent.parent.parent
ENV_PATH = BACKEND_DIR / ".env"
load_dotenv(ENV_PATH)

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB_PATH = os.path.join(BASE_DIR, "database", "database_project", "bus_school.db")
CHROMA_PATH = os.path.join(BASE_DIR, "database", "vector_db")

# Google API Key from .env
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Embedding provider: 'google' or 'local' (sentence-transformers)
# Default to 'google' if API key exists, but can be overridden via EMBEDDING_PROVIDER env var
# Set EMBEDDING_PROVIDER=local to force local embeddings (useful if Google quota exceeded)
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "google" if GOOGLE_API_KEY else "local").lower()


class EntityType(str, Enum):
    """Types of entities that can be searched"""
    COURSE = "course"
    PROGRAM = "program"
    SPECIALTY = "specialty"
    ALL = "all"


@dataclass
class SearchResult:
    """Generic search result"""
    entity_type: EntityType
    entity_id: str
    title: str
    description: str
    metadata: Dict[str, Any]
    score: float
    match_type: str  # 'vector', 'keyword', or 'hybrid'


class VectorSearchService:
    """
    Hybrid search service for academic entities using embeddings + ChromaDB.
    
    Supports searching:
    - Courses (course descriptions, titles, instructors)
    - Programs (program descriptions, requirements)
    - Specialties (specialty descriptions, focus areas)
    
    Uses Google Embeddings or local Sentence Transformers based on EMBEDDING_PROVIDER env var.
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if VectorSearchService._initialized:
            return
        
        logger.info(f"Initializing VectorSearchService with {EMBEDDING_PROVIDER} embeddings...")
        
        # Initialize embeddings based on provider
        self._init_embeddings()
        
        # Initialize ChromaDB with persistent storage
        os.makedirs(CHROMA_PATH, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        
        # Create collections for each entity type
        self.collections = {
            EntityType.COURSE: self._get_or_create_collection("courses"),
            EntityType.PROGRAM: self._get_or_create_collection("programs"),
            EntityType.SPECIALTY: self._get_or_create_collection("specialties"),
        }
        
        # Build indexes if empty
        self._ensure_indexes()
        
        VectorSearchService._initialized = True
        logger.info("VectorSearchService initialized successfully")
    
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
                logger.warning(f"Google Embeddings failed (quota/API issue): {e}")
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
            metadata={"description": f"WPI Business School {name}"}
        )
    
    def _get_db_connection(self) -> sqlite3.Connection:
        """Get SQLite database connection"""
        return sqlite3.connect(DB_PATH)
    
    def _get_expected_dimension(self) -> int:
        """Get expected embedding dimension based on current model"""
        return 768 if self.embedding_type == "google" else 384
    
    def _check_dimension_mismatch(self) -> bool:
        """Check if existing index has different dimensions than current model"""
        try:
            # Try to get a sample from courses collection
            collection = self.collections[EntityType.COURSE]
            if collection.count() > 0:
                # Generate a test embedding
                test_embedding = self._embed_query("test")
                expected_dim = len(test_embedding)
                
                # Try a query to check dimension compatibility
                try:
                    collection.query(query_embeddings=[test_embedding], n_results=1)
                    return False  # No mismatch
                except Exception as e:
                    if "dimension" in str(e).lower():
                        logger.warning(f"Dimension mismatch detected: {e}")
                        return True
            return False
        except Exception as e:
            logger.warning(f"Error checking dimensions: {e}")
            return False
    
    def _ensure_indexes(self):
        """Build vector indexes if collections are empty or dimensions mismatch"""
        # Check for dimension mismatch
        if self._check_dimension_mismatch():
            logger.info("Rebuilding indexes due to embedding dimension mismatch...")
            self.rebuild_index(EntityType.ALL)
            return
        
        if self.collections[EntityType.COURSE].count() == 0:
            self._build_course_index()
        
        if self.collections[EntityType.PROGRAM].count() == 0:
            self._build_program_index()
        
        if self.collections[EntityType.SPECIALTY].count() == 0:
            self._build_specialty_index()
    
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
    
    def _build_course_index(self):
        """Build vector index for courses"""
        logger.info("Building course vector index...")
        
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT course_code, Course_Title, Course_Description, Subject, 
                   Credits, Instructors, Locations, Delivery_Mode
            FROM courses
            WHERE Course_Title IS NOT NULL
        """)
        
        courses = cursor.fetchall()
        conn.close()
        
        if not courses:
            logger.warning("No courses found to index")
            return
        
        ids = []
        documents = []
        metadatas = []
        
        for course in courses:
            code, title, desc, subject, credits, instructors, locations, delivery = course
            
            # Create rich searchable document
            doc_parts = [title or ""]
            if desc:
                doc_parts.append(desc)
            if subject:
                doc_parts.append(f"Subject: {subject}")
            if instructors:
                doc_parts.append(f"Taught by: {instructors}")
            
            document = " ".join(doc_parts)
            
            ids.append(code)
            documents.append(document)
            metadatas.append({
                "entity_type": EntityType.COURSE.value,
                "code": code,
                "title": title or "",
                "subject": subject or "",
                "credits": credits or 0,
                "instructors": instructors or "",
                "locations": locations or "",
                "delivery_mode": delivery or ""
            })
        
        # Generate embeddings and add to collection
        embeddings = self._embed_texts(documents)
        
        self.collections[EntityType.COURSE].add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        logger.info(f"Indexed {len(courses)} courses")
    
    def _build_program_index(self):
        """Build vector index for programs"""
        logger.info("Building program vector index...")
        
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, program_name, program_code, program_type, 
                   program_level, description, Requirements
            FROM programs
        """)
        
        programs = cursor.fetchall()
        conn.close()
        
        if not programs:
            logger.warning("No programs found to index")
            return
        
        ids = []
        documents = []
        metadatas = []
        
        for program in programs:
            pid, name, code, ptype, level, desc, requirements = program
            
            doc_parts = [name or ""]
            if desc:
                doc_parts.append(desc)
            if level:
                doc_parts.append(f"Level: {level}")
            if ptype:
                doc_parts.append(f"Type: {ptype}")
            
            document = " ".join(doc_parts)
            
            ids.append(str(pid))
            documents.append(document)
            metadatas.append({
                "entity_type": EntityType.PROGRAM.value,
                "id": pid,
                "name": name or "",
                "code": code or "",
                "type": ptype or "",
                "level": level or "",
                "requirements": requirements or 0
            })
        
        embeddings = self._embed_texts(documents)
        
        self.collections[EntityType.PROGRAM].add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        logger.info(f"Indexed {len(programs)} programs")
    
    def _build_specialty_index(self):
        """Build vector index for specialties"""
        logger.info("Building specialty vector index...")
        
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.id, s.specialty_name, s.description, s.Requirements,
                   p.program_name, p.program_code
            FROM specialties s
            JOIN programs p ON s.program_id = p.id
        """)
        
        specialties = cursor.fetchall()
        conn.close()
        
        if not specialties:
            logger.warning("No specialties found to index")
            return
        
        ids = []
        documents = []
        metadatas = []
        
        for specialty in specialties:
            sid, name, desc, requirements, program_name, program_code = specialty
            
            doc_parts = [name or ""]
            if desc:
                doc_parts.append(desc)
            doc_parts.append(f"Part of {program_name} ({program_code})")
            
            document = " ".join(doc_parts)
            
            ids.append(str(sid))
            documents.append(document)
            metadatas.append({
                "entity_type": EntityType.SPECIALTY.value,
                "id": sid,
                "name": name or "",
                "program_name": program_name or "",
                "program_code": program_code or "",
                "requirements": requirements or 0
            })
        
        embeddings = self._embed_texts(documents)
        
        self.collections[EntityType.SPECIALTY].add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        logger.info(f"Indexed {len(specialties)} specialties")
    
    def rebuild_index(self, entity_type: EntityType = EntityType.ALL):
        """Force rebuild vector indexes"""
        logger.info(f"Rebuilding index for: {entity_type}")
        
        if entity_type in [EntityType.ALL, EntityType.COURSE]:
            try:
                self.chroma_client.delete_collection("courses")
            except:
                pass
            self.collections[EntityType.COURSE] = self._get_or_create_collection("courses")
            self._build_course_index()
        
        if entity_type in [EntityType.ALL, EntityType.PROGRAM]:
            try:
                self.chroma_client.delete_collection("programs")
            except:
                pass
            self.collections[EntityType.PROGRAM] = self._get_or_create_collection("programs")
            self._build_program_index()
        
        if entity_type in [EntityType.ALL, EntityType.SPECIALTY]:
            try:
                self.chroma_client.delete_collection("specialties")
            except:
                pass
            self.collections[EntityType.SPECIALTY] = self._get_or_create_collection("specialties")
            self._build_specialty_index()
    
    def vector_search(
        self, 
        query: str, 
        entity_type: EntityType = EntityType.ALL,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across entities.
        
        Args:
            query: Natural language query
            entity_type: Type of entity to search (COURSE, PROGRAM, SPECIALTY, or ALL)
            top_k: Number of results per entity type
            
        Returns:
            List of matching entities with scores
        """
        # Generate query embedding using appropriate method
        query_embedding = self._embed_query(query)
        
        results = []
        
        # Determine which collections to search
        if entity_type == EntityType.ALL:
            collections_to_search = [
                (EntityType.COURSE, self.collections[EntityType.COURSE]),
                (EntityType.PROGRAM, self.collections[EntityType.PROGRAM]),
                (EntityType.SPECIALTY, self.collections[EntityType.SPECIALTY]),
            ]
        else:
            collections_to_search = [(entity_type, self.collections[entity_type])]
        
        for etype, collection in collections_to_search:
            if collection.count() == 0:
                continue
            
            search_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count())
            )
            
            if search_results['ids'] and search_results['ids'][0]:
                for i, entity_id in enumerate(search_results['ids'][0]):
                    metadata = search_results['metadatas'][0][i] if search_results['metadatas'] else {}
                    distance = search_results['distances'][0][i] if search_results['distances'] else 1.0
                    
                    # Convert distance to similarity score
                    score = 1 / (1 + distance)
                    
                    results.append({
                        "entity_type": etype.value,
                        "entity_id": entity_id,
                        "metadata": metadata,
                        "score": score,
                        "match_type": "vector"
                    })
        
        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
    
    def keyword_search(
        self, 
        query: str, 
        entity_type: EntityType = EntityType.ALL,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Keyword-based search in database.
        
        Args:
            query: Search keywords
            entity_type: Type of entity to search
            top_k: Number of results
            
        Returns:
            List of matching entities
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()
        results = []
        search_term = f"%{query}%"
        
        if entity_type in [EntityType.ALL, EntityType.COURSE]:
            cursor.execute("""
                SELECT course_code, Course_Title, Course_Description, Subject, 
                       Credits, Instructors
                FROM courses
                WHERE course_code LIKE ? 
                   OR Course_Title LIKE ?
                   OR Subject LIKE ?
                   OR Instructors LIKE ?
                LIMIT ?
            """, (search_term, search_term, search_term, search_term, top_k))
            
            for row in cursor.fetchall():
                code, title, desc, subject, credits, instructors = row
                results.append({
                    "entity_type": EntityType.COURSE.value,
                    "entity_id": code,
                    "metadata": {
                        "code": code,
                        "title": title or "",
                        "description": desc or "",
                        "subject": subject or "",
                        "credits": credits or 0,
                        "instructors": instructors or ""
                    },
                    "score": 0.9 if query.lower() in (code or "").lower() else 0.7,
                    "match_type": "keyword"
                })
        
        if entity_type in [EntityType.ALL, EntityType.PROGRAM]:
            cursor.execute("""
                SELECT id, program_name, program_code, description
                FROM programs
                WHERE program_name LIKE ? OR program_code LIKE ?
                LIMIT ?
            """, (search_term, search_term, top_k))
            
            for row in cursor.fetchall():
                pid, name, code, desc = row
                results.append({
                    "entity_type": EntityType.PROGRAM.value,
                    "entity_id": str(pid),
                    "metadata": {
                        "id": pid,
                        "name": name or "",
                        "code": code or "",
                        "description": desc or ""
                    },
                    "score": 0.9 if query.lower() in (code or "").lower() else 0.7,
                    "match_type": "keyword"
                })
        
        if entity_type in [EntityType.ALL, EntityType.SPECIALTY]:
            cursor.execute("""
                SELECT s.id, s.specialty_name, s.description, p.program_name
                FROM specialties s
                JOIN programs p ON s.program_id = p.id
                WHERE s.specialty_name LIKE ?
                LIMIT ?
            """, (search_term, top_k))
            
            for row in cursor.fetchall():
                sid, name, desc, program_name = row
                results.append({
                    "entity_type": EntityType.SPECIALTY.value,
                    "entity_id": str(sid),
                    "metadata": {
                        "id": sid,
                        "name": name or "",
                        "description": desc or "",
                        "program_name": program_name or ""
                    },
                    "score": 0.8,
                    "match_type": "keyword"
                })
        
        conn.close()
        return results[:top_k]
    
    def hybrid_search(
        self, 
        query: str, 
        entity_type: EntityType = EntityType.ALL,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Combined vector + keyword search with result fusion.
        
        Args:
            query: Search query
            entity_type: Type of entity to search
            top_k: Number of results
            
        Returns:
            Merged and ranked results
        """
        vector_results = self.vector_search(query, entity_type, top_k * 2)
        keyword_results = self.keyword_search(query, entity_type, top_k * 2)
        
        # Merge by entity_id + entity_type
        merged = {}
        
        for result in keyword_results:
            key = f"{result['entity_type']}:{result['entity_id']}"
            merged[key] = {
                **result,
                "keyword_score": result["score"],
                "vector_score": 0.0,
            }
        
        for result in vector_results:
            key = f"{result['entity_type']}:{result['entity_id']}"
            if key in merged:
                merged[key]["vector_score"] = result["score"]
                merged[key]["match_type"] = "hybrid"
                # Weighted combination
                merged[key]["score"] = 0.5 * merged[key]["keyword_score"] + 0.5 * result["score"]
            else:
                merged[key] = {
                    **result,
                    "keyword_score": 0.0,
                    "vector_score": result["score"],
                }
        
        # Sort by score
        sorted_results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
        
        # Enrich results with full details from database
        enriched_results = self._enrich_results(sorted_results[:top_k])
        return enriched_results
    
    def _enrich_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fetch full details from database for search results"""
        if not results:
            return []
        
        conn = self._get_db_connection()
        cursor = conn.cursor()
        enriched = []
        
        for result in results:
            etype = result["entity_type"]
            entity_id = result["entity_id"]
            
            if etype == EntityType.COURSE.value:
                cursor.execute("""
                    SELECT course_code, Course_Title, Course_Description, Subject,
                           Credits, Instructors, Locations, Delivery_Mode, Academic_Level
                    FROM courses WHERE course_code = ?
                """, (entity_id,))
                row = cursor.fetchone()
                if row:
                    result["metadata"] = {
                        "code": row[0],
                        "title": row[1] or "",
                        "description": row[2] or "",
                        "subject": row[3] or "",
                        "credits": row[4] or 0,
                        "instructors": row[5] or "",
                        "locations": row[6] or "",
                        "delivery_mode": row[7] or "",
                        "academic_level": row[8] or ""
                    }
            
            elif etype == EntityType.PROGRAM.value:
                cursor.execute("""
                    SELECT id, program_name, program_code, program_type,
                           program_level, description, Requirements
                    FROM programs WHERE id = ?
                """, (int(entity_id),))
                row = cursor.fetchone()
                if row:
                    result["metadata"] = {
                        "id": row[0],
                        "name": row[1] or "",
                        "code": row[2] or "",
                        "type": row[3] or "",
                        "level": row[4] or "",
                        "description": row[5] or "",
                        "requirements": row[6] or 0
                    }
            
            elif etype == EntityType.SPECIALTY.value:
                cursor.execute("""
                    SELECT s.id, s.specialty_name, s.description, s.Requirements,
                           p.program_name, p.program_code
                    FROM specialties s
                    JOIN programs p ON s.program_id = p.id
                    WHERE s.id = ?
                """, (int(entity_id),))
                row = cursor.fetchone()
                if row:
                    result["metadata"] = {
                        "id": row[0],
                        "name": row[1] or "",
                        "description": row[2] or "",
                        "requirements": row[3] or 0,
                        "program_name": row[4] or "",
                        "program_code": row[5] or ""
                    }
            
            enriched.append(result)
        
        conn.close()
        return enriched
    
    def search(
        self, 
        query: str, 
        entity_type: EntityType = EntityType.ALL,
        top_k: int = 5
    ) -> str:
        """
        Main search interface - returns formatted string for agent.
        
        Args:
            query: Search query
            entity_type: Type to search (course/program/specialty/all)
            top_k: Number of results
            
        Returns:
            Formatted search results
        """
        results = self.hybrid_search(query, entity_type, top_k)
        
        if not results:
            return f"No results found for '{query}'."
        
        output = [f"Found {len(results)} result(s) for '{query}':\n"]
        
        for i, result in enumerate(results, 1):
            etype = result["entity_type"]
            metadata = result["metadata"]
            
            if etype == EntityType.COURSE.value:
                output.append(f"\n{i}. **[Course] {metadata.get('code', '')} - {metadata.get('title', '')}**")
                output.append(f"   - Subject: {metadata.get('subject', 'N/A')}")
                output.append(f"   - Credits: {metadata.get('credits', 'N/A')}")
                if metadata.get('instructors'):
                    output.append(f"   - Instructor(s): {metadata.get('instructors')}")
                if metadata.get('locations'):
                    output.append(f"   - Location: {metadata.get('locations')}")
                if metadata.get('description'):
                    # Clean HTML tags and truncate
                    desc = metadata['description'].replace('<p>', '').replace('</p>', ' ')
                    desc = desc[:250] + "..." if len(desc) > 250 else desc
                    output.append(f"   - Description: {desc}")
                    
            elif etype == EntityType.PROGRAM.value:
                output.append(f"\n{i}. **[Program] {metadata.get('name', '')} ({metadata.get('code', '')})**")
                if metadata.get('level'):
                    output.append(f"   - Level: {metadata.get('level')}")
                if metadata.get('description'):
                    desc = metadata['description'][:200] + "..." if len(metadata['description']) > 200 else metadata['description']
                    output.append(f"   - Description: {desc}")
                    
            elif etype == EntityType.SPECIALTY.value:
                output.append(f"\n{i}. **[Specialty] {metadata.get('name', '')}**")
                output.append(f"   - Program: {metadata.get('program_name', 'N/A')} ({metadata.get('program_code', '')})")
                if metadata.get('description'):
                    desc = metadata['description'][:200] + "..." if len(metadata['description']) > 200 else metadata['description']
                    output.append(f"   - Description: {desc}")
        
        return "\n".join(output)
    
    def search_courses(self, query: str, top_k: int = 5) -> str:
        """Convenience method for course-only search"""
        return self.search(query, EntityType.COURSE, top_k)
    
    def search_programs(self, query: str, top_k: int = 5) -> str:
        """Convenience method for program-only search"""
        return self.search(query, EntityType.PROGRAM, top_k)
    
    def search_specialties(self, query: str, top_k: int = 5) -> str:
        """Convenience method for specialty-only search"""
        return self.search(query, EntityType.SPECIALTY, top_k)


# Singleton instance
_service_instance: Optional[VectorSearchService] = None


def get_vector_search_service() -> VectorSearchService:
    """Get singleton instance of VectorSearchService"""
    global _service_instance
    if _service_instance is None:
        _service_instance = VectorSearchService()
    return _service_instance
