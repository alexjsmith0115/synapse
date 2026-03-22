"""
Shared fixtures for integration tests.

Requires Memgraph on localhost:7687 and .NET SDK.
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

PYTHON_FIXTURE_PATH = str(
    (pathlib.Path(__file__).parent.parent / "fixtures" / "SynapsePyTest").resolve()
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


def _delete_project(conn: GraphConnection, path: str) -> None:
    """Delete only the specified project's nodes from the graph."""
    conn.execute(
        "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n) DETACH DELETE n",
        {"path": path},
    )
    conn.execute(
        "MATCH (r:Repository {path: $path}) DELETE r",
        {"path": path},
    )


@pytest.fixture(scope="session")
def service():
    conn = GraphConnection.create(database="memgraph")
    ensure_schema(conn)
    _delete_project(conn, FIXTURE_PATH)

    svc = SynapseService(conn=conn)
    svc.index_project(FIXTURE_PATH, "csharp")

    yield svc

    _delete_project(conn, FIXTURE_PATH)


@pytest.fixture(scope="session")
def mcp_server(service):
    mcp = FastMCP("synapse-test")
    register_tools(mcp, service)
    return mcp


@pytest.fixture(scope="session")
def python_service():
    """Index the Python fixture project and yield SynapseService."""
    conn = GraphConnection.create(database="memgraph")
    ensure_schema(conn)
    _delete_project(conn, PYTHON_FIXTURE_PATH)
    svc = SynapseService(conn=conn)
    svc.index_project(PYTHON_FIXTURE_PATH, "python")
    yield svc
    _delete_project(conn, PYTHON_FIXTURE_PATH)


@pytest.fixture(scope="session")
def python_mcp(python_service):
    """Return MCP server instance wired to the Python-indexed graph."""
    mcp = FastMCP("synapse-python-test")
    register_tools(mcp, python_service)
    return mcp


JAVA_FIXTURE_PATH = str(
    (pathlib.Path(__file__).parent.parent / "fixtures" / "SynapseJavaTest").resolve()
)

TYPESCRIPT_FIXTURE_PATH = str(
    (pathlib.Path(__file__).parent.parent / "fixtures" / "SynapseJSTest").resolve()
)


@pytest.fixture(scope="session")
def typescript_service():
    """Index the TypeScript fixture project and yield SynapseService."""
    conn = GraphConnection.create(database="memgraph")
    ensure_schema(conn)
    _delete_project(conn, TYPESCRIPT_FIXTURE_PATH)
    svc = SynapseService(conn=conn)
    svc.index_project(TYPESCRIPT_FIXTURE_PATH, "typescript")
    yield svc
    _delete_project(conn, TYPESCRIPT_FIXTURE_PATH)


@pytest.fixture(scope="session")
def typescript_mcp(typescript_service):
    """Return MCP server instance wired to the TypeScript-indexed graph."""
    mcp = FastMCP("synapse-typescript-test")
    register_tools(mcp, typescript_service)
    return mcp


@pytest.fixture(scope="session")
def java_service():
    """Index the Java fixture project and yield SynapseService."""
    conn = GraphConnection.create(database="memgraph")
    ensure_schema(conn)
    _delete_project(conn, JAVA_FIXTURE_PATH)
    svc = SynapseService(conn=conn)
    svc.index_project(JAVA_FIXTURE_PATH, "java")
    yield svc
    _delete_project(conn, JAVA_FIXTURE_PATH)


@pytest.fixture(scope="session")
def java_mcp(java_service):
    """Return MCP server instance wired to the Java-indexed graph."""
    mcp = FastMCP("synapse-java-test")
    register_tools(mcp, java_service)
    return mcp
