"""
Admin API endpoints for maintenance tasks.
"""
from fastapi import APIRouter, HTTPException
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/rebuild-pdf-index")
async def rebuild_pdf_index():
    """
    Rebuild the PDF vector index from source PDF files.
    
    This will:
    1. Delete the existing ChromaDB collection
    2. Re-extract text from all PDF files
    3. Re-chunk and embed all content
    4. Store in a fresh ChromaDB collection
    
    Useful when PDF files are updated.
    """
    try:
        from ..services.pdf_vector_service import get_pdf_vector_service
        
        logger.info("Admin: Rebuilding PDF vector index...")
        service = get_pdf_vector_service()
        
        # Get stats before
        before_stats = service.get_stats()
        
        # Rebuild
        service.rebuild_index()
        
        # Get stats after
        after_stats = service.get_stats()
        
        return {
            "status": "success",
            "message": "PDF vector index rebuilt successfully",
            "before": {"total_chunks": before_stats["total_chunks"]},
            "after": {"total_chunks": after_stats["total_chunks"]},
            "pdf_files": after_stats["pdf_files"],
            "embedding_type": after_stats["embedding_type"],
        }
        
    except Exception as e:
        logger.error(f"Error rebuilding PDF index: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to rebuild index: {str(e)}")


@router.get("/pdf-index-stats")
async def get_pdf_index_stats():
    """
    Get statistics about the PDF vector index.
    """
    try:
        from ..services.pdf_vector_service import get_pdf_vector_service
        
        service = get_pdf_vector_service()
        stats = service.get_stats()
        
        return {
            "status": "success",
            **stats
        }
        
    except Exception as e:
        logger.error(f"Error getting PDF index stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/test-pdf-search")
async def test_pdf_search(query: str = "MBA program requirements", top_k: int = 10):
    """
    Test the PDF vector search with a sample query.
    """
    try:
        from ..services.pdf_vector_service import get_pdf_vector_service
        
        service = get_pdf_vector_service()
        results = service.search(query, top_k=top_k)
        
        return {
            "status": "success",
            "query": query,
            "results_count": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error testing PDF search: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
