"""
MCP tool integration tests.

Requires FalkorDB on localhost:6379 and .NET SDK.
Run with: pytest tests/mcp/ -v -m integration
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest
from mcp.server.fastmcp import FastMCP

from synapse.graph.connection import GraphConnection
from synapse.graph.schema import ensure_schema
from synapse.mcp.tools import register_tools
from synapse.service import SynapseService

FIXTURE_PATH = str(pathlib.Path(__file__).parent.parent / "fixtures" / "SynapseTest")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine from a synchronous test."""
    return asyncio.run(coro)


def _content(result) -> list:
    """Extract the content list from a call_tool result.

    FastMCP 1.26 returns either (content_list, structured_dict) or bare
    content_list depending on the tool's return type annotation.
    """
    return result[0] if isinstance(result, tuple) else result


def _text(result) -> str:
    return _content(result)[0].text


def _json(result):
    return json.loads(_text(result))


# ---------------------------------------------------------------------------
# Module-scoped fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mcp_server():
    conn = GraphConnection.create(graph_name="synapse_test_mcp")
    ensure_schema(conn)
    conn.execute("MATCH (n) DETACH DELETE n")  # scoped to synapse_test_mcp graph

    service = SynapseService(conn=conn)
    mcp = FastMCP("synapse-test")
    register_tools(mcp, service)

    service.index_project(FIXTURE_PATH, "csharp")

    yield mcp

    conn.execute("MATCH (n) DETACH DELETE n")  # scoped to synapse_test_mcp graph
    # GraphConnection has no close() — connection released by GC


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "index_project", "list_projects", "delete_project", "get_index_status",
    "get_symbol", "get_symbol_source", "find_implementations", "find_callers",
    "find_callees", "get_hierarchy", "search_symbols", "set_summary",
    "get_summary", "list_summarized", "execute_query", "watch_project",
    "unwatch_project", "find_type_references", "find_dependencies",
    "get_context_for",
}


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_all_tools_registered(mcp_server: FastMCP) -> None:
    tools = _run(mcp_server.list_tools())
    names = {t.name for t in tools}
    assert EXPECTED_TOOLS == names


# ---------------------------------------------------------------------------
# Project-level tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_projects(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("list_projects", {}))
    projects = _json(result)
    paths = [p["path"] for p in projects]
    assert FIXTURE_PATH in paths


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_index_status(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("get_index_status", {"path": FIXTURE_PATH}))
    status = _json(result)
    assert status["file_count"] > 0
    assert status["symbol_count"] > 0
