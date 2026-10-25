"""
Protocol-level tests for the MCP server (mcp_server/server.py).

Uses the SDK's in-process Client, so every call goes through real MCP
list/call/read round-trips against the bundled SQLite database.
"""
import json
from unittest.mock import patch

import pytest

# The MCP SDK lives in its own venv (it needs a newer starlette than the backend);
# run these with: .venv-mcp/bin/python -m pytest tests/test_mcp_server.py
pytest.importorskip("mcp")
from mcp import Client  # noqa: E402

from mcp_server.server import mcp  # noqa: E402

EXPECTED_TOOLS = {
    "search_courses",
    "get_course",
    "search_programs",
    "get_program_structure",
    "check_degree_progress",
    "search_catalog",
    "get_catalog_context",
}


def _text(result) -> str:
    return "\n".join(c.text for c in result.content if c.type == "text")


# Each test opens its own Client: anyio cancel scopes must be entered and
# exited in the same task, which an async yield-fixture does not guarantee.


async def test_lists_all_tools_as_read_only():
    async with Client(mcp) as client:
        tools = (await client.list_tools()).tools
        assert {t.name for t in tools} == EXPECTED_TOOLS
        for tool in tools:
            assert tool.description, f"{tool.name} has no description"
            assert tool.annotations.read_only_hint is True


async def test_check_degree_progress_schema_takes_course_lists():
    async with Client(mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        schema = tools["check_degree_progress"].input_schema
        assert set(schema["required"]) == {"program", "completed_courses"}
        assert schema["properties"]["completed_courses"]["type"] == "array"


async def test_get_course_returns_structured_record():
    async with Client(mcp) as client:
        result = await client.call_tool("get_course", {"course_code": "MIS 571"})
        assert not result.is_error
        record = result.structured_content["result"]
        assert record["code"] == "MIS 571"
        assert record["title"]
        assert record["credits"]


async def test_get_course_unknown_code_returns_null():
    async with Client(mcp) as client:
        result = await client.call_tool("get_course", {"course_code": "ZZZ 999"})
        assert not result.is_error
        assert result.structured_content["result"] is None


async def test_check_degree_progress_reports_missing_requirements():
    async with Client(mcp) as client:
        result = await client.call_tool(
            "check_degree_progress",
            {"program": "MSIT", "completed_courses": ["MIS 500", "MIS 571"], "current_courses": ["MIS 584"]},
        )
        report = _text(result)
        assert not result.is_error
        assert "PROGRAM COMPLETION ANALYSIS" in report
        assert "MIS 571" in report
        assert "Currently Taking: MIS 584" in report


async def test_get_program_structure_overview():
    async with Client(mcp) as client:
        result = await client.call_tool("get_program_structure", {"program": "MSIT"})
        assert not result.is_error
        assert "Information Technology" in _text(result)


async def test_programs_resource_lists_every_program():
    async with Client(mcp) as client:
        resources = (await client.list_resources()).resources
        assert [str(r.uri) for r in resources] == ["adviser://programs"]

        contents = (await client.read_resource("adviser://programs")).contents
        programs = json.loads(contents[0].text)
        assert len(programs) >= 1
        assert all({"program_id", "program_name"} <= p.keys() for p in programs)


async def test_search_tools_delegate_to_shared_search_layer():
    async with Client(mcp) as client:
        # The vector store is heavy to build in CI; verify wiring, not retrieval quality.
        with patch("app.services.search_service.smart_course_search_tool", return_value="COURSE HIT") as course, \
             patch("app.services.search_service.semantic_search_tool", return_value="CATALOG HIT") as catalog:
            assert _text(await client.call_tool("search_courses", {"query": "MIS 571"})) == "COURSE HIT"
            assert _text(await client.call_tool("search_catalog", {"query": "thesis option"})) == "CATALOG HIT"
        course.assert_called_once_with("MIS 571")
        catalog.assert_called_once_with("thesis option")


async def test_stray_stdout_is_kept_off_the_protocol_stream(capsys):
    async with Client(mcp) as client:
        def noisy(query):
            print("loading embeddings...")
            return "ok"

        with patch("app.services.search_service.program_search_tool", side_effect=noisy):
            result = await client.call_tool("search_programs", {"query": "MBA"})

        assert _text(result) == "ok"
        captured = capsys.readouterr()
        assert "loading embeddings" not in captured.out
        assert "loading embeddings" in captured.err
