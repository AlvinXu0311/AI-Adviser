"""
Admin API endpoints for maintenance tasks.
"""
from fastapi import APIRouter, Depends, HTTPException
import asyncio
import logging

from ..auth import require_admin

logger = logging.getLogger(__name__)

# Every admin route requires a token whose email is listed in ADMIN_EMAILS
router = APIRouter(dependencies=[Depends(require_admin)])


@router.post("/rebuild-pdf-index")
async def rebuild_pdf_index(activate: bool = True):
    """
    Build a new PDF vector index version offline and switch to it.

    The active index keeps serving the whole time: the new version is written to its own
    directory, validated, and only then activated (all workers move over within seconds).
    Pass activate=false to build and validate without switching.
    """
    from ..services import vector_index

    logger.info("Admin: building a new PDF vector index version...")
    try:
        manifest = await asyncio.to_thread(vector_index.build, activate)
    except vector_index.BuildInProgress:
        raise HTTPException(status_code=409, detail="An index build is already running")
    except vector_index.IndexBuildError as e:
        # Validation failures are meant for the admin: the catalog or embeddings need attention
        logger.error(f"New PDF index failed validation: {e}")
        raise HTTPException(status_code=422, detail=f"New index rejected, active index unchanged: {e}")
    except Exception as e:
        logger.error(f"Error building PDF index: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to build index; active index unchanged")

    return {"status": "success", "activated": activate, **manifest}


@router.get("/pdf-index-versions")
async def list_pdf_index_versions():
    """All built index versions, newest last, with which one is active."""
    from ..services import vector_index
    return {"versions": await asyncio.to_thread(vector_index.list_versions)}


@router.post("/pdf-index-versions/{version}/activate")
async def activate_pdf_index_version(version: str):
    """Serve an existing version, e.g. to roll back a bad catalog update."""
    from ..services import vector_index
    try:
        await asyncio.to_thread(vector_index.activate, version)
    except ValueError:
        raise HTTPException(status_code=404, detail="No complete index version with that name")
    return {"status": "success", "active": version}


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
        logger.error(f"Error getting PDF index stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get stats")


@router.post("/test-pdf-search")
async def test_pdf_search(query: str = "MBA program requirements", top_k: int = 10):
    """
    Test the PDF vector search with a sample query.
    """
    try:
        from ..services.pdf_vector_service import get_pdf_vector_service
        
        service = get_pdf_vector_service()
        results = await asyncio.to_thread(service.search, query, top_k=min(top_k, 50))
        
        return {
            "status": "success",
            "query": query,
            "results_count": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error testing PDF search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Search failed")
