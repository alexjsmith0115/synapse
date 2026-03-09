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
    conn.execute("MATCH (n) DETACH DELETE n")

    service = SynapseService(conn=conn)
    mcp = FastMCP("synapse-test")
    register_tools(mcp, service)

    service.index_project(FIXTURE_PATH, "csharp")

    yield mcp

    conn.execute("MATCH (n) DETACH DELETE n")
