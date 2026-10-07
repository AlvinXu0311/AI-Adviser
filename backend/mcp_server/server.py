"""
MCP server for the WPI Business School academic adviser.

Exposes the adviser's retrieval layer (SQLite program DB + ChromaDB PDF catalog)
as Model Context Protocol tools, so any MCP client — Claude Code, Claude Desktop,
Cursor, Dify — can use the same course/program/degree-audit capabilities as the
in-app ReAct agent.

Unlike the in-app tools, nothing here depends on a chat session: student data
(completed / current courses) is passed in explicitly by the client.

Run from the backend/ directory:
    python -m mcp_server.server                       # stdio (default)
    python -m mcp_server.server --transport streamable-http --port 8765
"""
from __future__ import annotations

import argparse
import contextlib
import logging
import sys
from typing import Any, Callable, Dict, List, Optional, TypeVar

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from app.services import search_service
from app.services.program_db_service import get_program_db_service

load_dotenv()

# stdio transport owns stdout; keep all logging on stderr.
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("adviser-mcp")

T = TypeVar("T")

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

mcp = MCPServer(
    name="wpi-adviser",
    title="WPI Business School Adviser",
    instructions=(
        "Authoritative data for WPI Business School graduate programs and courses. "
        "Prefer get_course / search_courses / get_program_structure (database-backed) "
        "over search_catalog (PDF semantic search), and cite which tool each fact came from. "
        "check_degree_progress needs the student's course codes, e.g. ['MIS 571', 'BUS 500']."
    ),
)


def _quiet(fn: Callable[[], T]) -> T:
    """Run a call with stdout redirected to stderr.

    Third-party libraries (ChromaDB, sentence-transformers) may print on first
    load; on the stdio transport that would corrupt the JSON-RPC stream.
    """
    with contextlib.redirect_stdout(sys.stderr):
        return fn()


@mcp.tool(annotations=READ_ONLY)
def search_courses(query: str) -> str:
    """Find courses by code, title, topic, or instructor.

    Searches the program database first (instructor, credits, delivery mode,
    offering term), then the PDF course catalogs for descriptions and
    prerequisites. Examples: "MIS 571", "machine learning", "who teaches FIN 500".
    """
    return _quiet(lambda: search_service.smart_course_search_tool(query))


@mcp.tool(annotations=READ_ONLY)
def get_course(course_code: str) -> Optional[Dict[str, Any]]:
    """Get the database record for one course by exact code (e.g. "MIS 571").

    Returns null when the code is not in the database; fall back to
    search_courses in that case (cross-listed or non-business courses).
    """
    return _quiet(lambda: get_program_db_service().get_course_by_code(course_code))


@mcp.tool(annotations=READ_ONLY)
def search_programs(query: str) -> str:
    """Search degree programs (MBA, MSIT, MSBA, ...) for requirements,
    specialties/concentrations, and degree structure, using the database
    first and the graduate catalog PDF as fallback."""
    return _quiet(lambda: search_service.program_search_tool(query))


@mcp.tool(annotations=READ_ONLY)
def get_program_structure(program: str) -> str:
    """Official program structure from the database: required and optional
    specialties and the courses that satisfy each. Pass a program code such
    as "MSIT" or "MBA", or "all" for an overview of every program."""
    return _quiet(lambda: search_service.business_school_db_tool(program))


@mcp.tool(annotations=READ_ONLY)
def check_degree_progress(
    program: str,
    completed_courses: List[str],
    current_courses: Optional[List[str]] = None,
) -> str:
    """Audit a student's courses against a program's graduation requirements.

    Args:
        program: Program code or name, e.g. "MSIT", "MBA", "MSBA".
        completed_courses: Course codes already passed, e.g. ["MIS 500", "BUS 500"].
        current_courses: Course codes in progress this term (counted separately).

    Returns a report of completed and missing required/optional specialties
    and the remaining courses for each.
    """
    def run() -> str:
        service = get_program_db_service()
        analysis = service.compare_student_progress(program, completed_courses, current_courses or [])
        return service.format_progress_report(analysis)

    return _quiet(run)


@mcp.tool(annotations=READ_ONLY)
def search_catalog(query: str) -> str:
    """Semantic search over the academic PDF catalogs (business, graduate
    programs, math, CS). Use as a fallback when the database-backed tools
    return nothing."""
    return _quiet(lambda: search_service.semantic_search_tool(query))


@mcp.tool(annotations=READ_ONLY)
def get_catalog_context(query: str) -> str:
    """Longer, concatenated catalog excerpts (up to ~4000 chars) for questions
    that need policy text or detailed requirements from several sources."""
    return _quiet(lambda: search_service.pdf_context_tool(query))


@mcp.resource(
    "adviser://programs",
    name="programs",
    description="All graduate programs in the Business School database.",
    mime_type="application/json",
)
def list_programs() -> List[Dict[str, Any]]:
    return [
        {"program_id": p["program_id"], "program_name": p["program_name"], "notes": p["program_notes"]}
        for p in get_program_db_service().get_all_programs()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run("stdio")
    else:
        mcp.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
