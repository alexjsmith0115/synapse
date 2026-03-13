"""
Shared fixtures for integration tests.

Requires FalkorDB on localhost:6379 and .NET SDK.
Run with: pytest tests/integration/ -v -m integration
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

FIXTURE_PATH = str(
    (pathlib.Path(__file__).parent.parent / "fixtures" / "SynapseTest").resolve()
)


def run(coro):
    """Run an async coroutine from a synchronous test."""
    return asyncio.run(coro)


def content(result) -> list:
    """Extract the content list from a call_tool result.

    FastMCP 1.26 returns either (content_list, structured_dict) or bare
    content_list depending on the tool's return type annotation.
    """
    return result[0] if isinstance(result, tuple) else result


def text(result) -> str:
    return content(result)[0].text


def result_json(result):
    """Parse the result of a call_tool call to a Python object.

    FastMCP 1.26 emits one TextContent block per list element, making
    text-based parsing unreliable for lists. The structured result
    (tuple's second element) always contains the full return value.
    """
    if isinstance(result, tuple):
        return result[1].get("result")
    if result:
        return json.loads(result[0].text)
    return None


@pytest.fixture(scope="session")
def service():
    conn = GraphConnection.create(graph_name="synapse_integration_test")
    ensure_schema(conn)
    conn.execute("MATCH (n) DETACH DELETE n")

    svc = SynapseService(conn=conn)
    svc.index_project(FIXTURE_PATH, "csharp")

    yield svc

    conn.execute("MATCH (n) DETACH DELETE n")


@pytest.fixture(scope="session")
def mcp_server(service):
    mcp = FastMCP("synapse-test")
    register_tools(mcp, service)
    return mcp
