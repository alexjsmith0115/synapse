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


# ---------------------------------------------------------------------------
# Symbol query tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("get_symbol", {"full_name": "SynapseTest.Dog"}))
    symbol = _json(result)
    assert symbol is not None
    assert symbol["full_name"] == "SynapseTest.Dog"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_not_found(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("get_symbol", {"full_name": "DoesNotExist.Nope"}))
    assert _json(result) is None


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_source(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("get_symbol_source", {"full_name": "SynapseTest.Animal"}))
    source = _text(result)
    assert "Animal" in source
    assert "abstract" in source.lower() or "IAnimal" in source


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols(mcp_server: FastMCP) -> None:
    # search_symbols matches on node name (substring), not full_name
    result = _run(mcp_server.call_tool("search_symbols", {"query": "Animal"}))
    symbols = _json(result)
    names = [s["full_name"] for s in symbols]
    assert len(symbols) >= 1
    assert any("Animal" in n for n in names)

    result2 = _run(mcp_server.call_tool("search_symbols", {"query": "Dog"}))
    symbols2 = _json(result2)
    names2 = [s["full_name"] for s in symbols2]
    assert any("Dog" in n for n in names2)


# ---------------------------------------------------------------------------
# Relationship query tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_implementations(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("find_implementations", {"interface_name": "SynapseTest.IAnimal"}))
    impls = _json(result)
    names = [i["full_name"] for i in impls]
    assert "SynapseTest.Dog" in names
    assert "SynapseTest.Cat" in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callers(mcp_server: FastMCP) -> None:
    # Direct static call (Greeter.Greet -> Formatter.Format) is resolvable by the LSP
    result = _run(mcp_server.call_tool("find_callers", {"method_full_name": "SynapseTest.Formatter.Format"}))
    callers = _json(result)
    names = [c.get("full_name", "") for c in callers]
    assert any("Greet" in n for n in names), f"Expected Greeter.Greet in callers, got: {names}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callees(mcp_server: FastMCP) -> None:
    # Direct static call (Greeter.Greet -> Formatter.Format) is resolvable by the LSP
    result = _run(mcp_server.call_tool("find_callees", {"method_full_name": "SynapseTest.Greeter.Greet"}))
    callees = _json(result)
    names = [c.get("full_name", "") for c in callees]
    assert any("Format" in n for n in names), f"Expected Formatter.Format in callees, got: {names}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_hierarchy(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("get_hierarchy", {"class_name": "SynapseTest.Dog"}))
    hierarchy = _json(result)
    text = json.dumps(hierarchy)
    assert "Animal" in text


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_references(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("find_type_references", {"full_name": "SynapseTest.IAnimal"}))
    refs = _json(result)
    names = [r["symbol"].get("full_name", "") for r in refs]
    assert any("AnimalService" in n for n in names)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_dependencies(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("find_dependencies", {"full_name": "SynapseTest.AnimalService"}))
    deps = _json(result)
    names = [d["type"].get("full_name", "") for d in deps]
    assert any("IAnimal" in n for n in names)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("get_context_for", {"full_name": "SynapseTest.AnimalService"}))
    context = _text(result)
    assert len(context) > 0
    assert "AnimalService" in context


# ---------------------------------------------------------------------------
# Summary tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_set_and_get_summary(mcp_server: FastMCP) -> None:
    _run(mcp_server.call_tool("set_summary", {
        "full_name": "SynapseTest.Dog",
        "content": "Represents a dog in the test fixture.",
    }))
    result = _run(mcp_server.call_tool("get_summary", {"full_name": "SynapseTest.Dog"}))
    assert _text(result) == "Represents a dog in the test fixture."


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_summarized(mcp_server: FastMCP) -> None:
    _run(mcp_server.call_tool("set_summary", {
        "full_name": "SynapseTest.Dog",
        "content": "Represents a dog in the test fixture.",
    }))
    result = _run(mcp_server.call_tool("list_summarized", {}))
    items = _json(result)
    names = [i.get("full_name") for i in items]
    assert "SynapseTest.Dog" in names


# ---------------------------------------------------------------------------
# execute_query
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_valid_query(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("execute_query", {
        "cypher": "MATCH (n:Class) RETURN n.name LIMIT 5"
    }))
    rows = _json(result)
    assert isinstance(rows, list)
    assert len(rows) > 0, "Expected at least one Class node after indexing"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_mutating_query_raises(mcp_server: FastMCP) -> None:
    with pytest.raises(Exception):
        _run(mcp_server.call_tool("execute_query", {
            "cypher": "CREATE (n:Fake) RETURN n"
        }))


# ---------------------------------------------------------------------------
# Watch tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_watch_and_unwatch_project(mcp_server: FastMCP) -> None:
    watch_result = _run(mcp_server.call_tool("watch_project", {"path": FIXTURE_PATH}))
    assert FIXTURE_PATH in _text(watch_result)

    unwatch_result = _run(mcp_server.call_tool("unwatch_project", {"path": FIXTURE_PATH}))
    assert FIXTURE_PATH in _text(unwatch_result)
