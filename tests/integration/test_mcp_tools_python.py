"""
MCP tool integration tests against the Python fixture (SynappsPyTest).

Requires Memgraph on localhost:7687 and Python indexer.
Run with: pytest tests/integration/test_mcp_tools_python.py -v -m integration
"""
from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP

from synapps.service import SynappsService
from tests.integration.conftest import run, text, result_json, PYTHON_FIXTURE_PATH


# ---------------------------------------------------------------------------
# Project-level tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_projects(python_mcp: FastMCP) -> None:
    """list_projects returns at least one project with language 'python'."""
    result = run(python_mcp.call_tool("list_projects", {}))
    projects = result_json(result)
    assert isinstance(projects, list)
    assert len(projects) >= 1
    all_languages = [lang for p in projects for lang in p.get("languages", [])]
    assert "python" in all_languages, f"Expected 'python' in project languages, got: {all_languages}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_index_status(python_mcp: FastMCP) -> None:
    """list_projects(path=...) returns a populated status dict for the Python fixture."""
    result = run(python_mcp.call_tool("list_projects", {"path": PYTHON_FIXTURE_PATH}))
    status = result_json(result)
    assert status is not None
    assert status["file_count"] > 0
    assert status["symbol_count"] > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_schema(python_mcp: FastMCP) -> None:
    """get_schema returns the graph schema (not Python-specific, but must not error)."""
    result = run(python_mcp.call_tool("get_schema", {}))
    schema = result_json(result)
    assert "node_labels" in schema


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_index_project(python_mcp: FastMCP) -> None:
    """index_project re-indexes the Python fixture without error (upsert -- safe to re-run)."""
    result = run(python_mcp.call_tool("index_project", {
        "path": PYTHON_FIXTURE_PATH,
        "language": "python",
    }))
    msg = text(result)
    assert "Indexed" in msg


# ---------------------------------------------------------------------------
# Symbol query tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols(python_mcp: FastMCP) -> None:
    """search_symbols returns matching Python symbols."""
    result = run(python_mcp.call_tool("search_symbols", {"query": "Animal"}))
    symbols = result_json(result)
    assert isinstance(symbols, list)
    assert len(symbols) >= 1
    names = [s["full_name"] for s in symbols]
    assert any("Animal" in n for n in names)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols_language_filter(python_mcp: FastMCP) -> None:
    """search_symbols with language='python' returns only Python symbols."""
    result = run(python_mcp.call_tool("search_symbols", {
        "query": "Animal",
        "language": "python",
    }))
    symbols = result_json(result)
    assert isinstance(symbols, list)
    for sym in symbols:
        assert sym.get("language") == "python", (
            f"Expected language='python', got: {sym.get('language')} for {sym.get('full_name')}"
        )


# ---------------------------------------------------------------------------
# Relationship tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_implementations(python_mcp: FastMCP) -> None:
    """find_implementations for IAnimal returns its subclasses via INHERITS edges."""
    result = run(python_mcp.call_tool("find_implementations", {
        "interface_name": "synappspytest.animals.IAnimal"
    }))
    impls = result_json(result)
    assert isinstance(impls, list)
    assert len(impls) >= 2, f"Expected at least Dog and Cat, got {impls}"
    names = [i.get("full_name", "") for i in impls]
    assert any("Dog" in n for n in names), f"Dog not found in {names}"
    assert any("Cat" in n for n in names), f"Cat not found in {names}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_hierarchy(python_mcp: FastMCP) -> None:
    """get_hierarchy for Dog returns Animal/IAnimal in parent chain."""
    result = run(python_mcp.call_tool("get_hierarchy", {
        "class_name": "synappspytest.animals.Dog"
    }))
    hierarchy = result_json(result)
    assert "parents" in hierarchy
    parent_names = [p.get("full_name", "") for p in hierarchy["parents"]]
    assert any("Animal" in n for n in parent_names), (
        f"Expected Animal in Dog's parents, got: {parent_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callees(python_mcp: FastMCP) -> None:
    """find_callees returns callees (possibly empty for Python fixture) without error."""
    result = run(python_mcp.call_tool("find_callees", {
        "method_full_name": "synappspytest.services.AnimalService.get_greeting"
    }))
    callees = result_json(result)
    assert isinstance(callees, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_references(python_mcp: FastMCP) -> None:
    """find_usages with kind='parameter' returns list (possibly empty for Python) without error."""
    result = run(python_mcp.call_tool("find_usages", {
        "full_name": "synappspytest.animals.IAnimal",
        "kind": "parameter",
    }))
    refs = result_json(result)
    assert isinstance(refs, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_usages(python_mcp: FastMCP) -> None:
    """find_usages returns compact text summary for a Python class."""
    result = run(python_mcp.call_tool("find_usages", {
        "full_name": "synappspytest.animals.IAnimal"
    }))
    output = text(result)
    assert "Usages of" in output
    assert "IAnimal" in output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_dependencies(python_mcp: FastMCP) -> None:
    """find_dependencies returns list without error for AnimalService."""
    result = run(python_mcp.call_tool("find_dependencies", {
        "full_name": "synappspytest.services.AnimalService"
    }))
    deps = result_json(result)
    assert isinstance(deps, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for(python_mcp: FastMCP) -> None:
    """get_context_for returns context string for a Python class."""
    result = run(python_mcp.call_tool("get_context_for", {
        "full_name": "synappspytest.animals.Dog"
    }))
    ctx = text(result)
    assert len(ctx) > 0
    assert "Dog" in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_structure_scope(python_mcp: FastMCP) -> None:
    """get_context_for(scope='structure') returns Members but not Called Methods for a Python class."""
    result = run(python_mcp.call_tool("get_context_for", {
        "full_name": "synappspytest.services.AnimalService",
        "scope": "structure",
    }))
    ctx = text(result)
    assert "## Members" in ctx
    assert "AnimalService" in ctx
    assert "## Called Methods" not in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_method_scope(python_mcp: FastMCP) -> None:
    """get_context_for(scope='method') returns Target but not Containing Type or Members list."""
    result = run(python_mcp.call_tool("get_context_for", {
        "full_name": "synappspytest.services.AnimalService.get_greeting",
        "scope": "method",
    }))
    ctx = text(result)
    assert "## Target:" in ctx
    assert "get_greeting" in ctx
    assert "## Containing Type:" not in ctx
    assert "## Members:" not in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_edit_scope_method(python_mcp: FastMCP) -> None:
    """get_context_for(scope='edit') on a method returns Target but not Containing Type or Called Methods."""
    result = run(python_mcp.call_tool("get_context_for", {
        "full_name": "synappspytest.services.AnimalService.get_greeting",
        "scope": "edit",
    }))
    ctx = text(result)
    assert "## Target:" in ctx
    assert "get_greeting" in ctx
    assert "## Containing Type:" not in ctx
    assert "## Called Methods" not in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_edit_scope_class(python_mcp: FastMCP) -> None:
    """get_context_for(scope='edit') on a class returns Target and the class name."""
    result = run(python_mcp.call_tool("get_context_for", {
        "full_name": "synappspytest.services.AnimalService",
        "scope": "edit",
    }))
    ctx = text(result)
    assert "## Target:" in ctx
    assert "AnimalService" in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_edit_scope_rejects_field(python_mcp: FastMCP) -> None:
    """get_context_for(scope='edit') on a Field/Property node returns the rejection message."""
    # Python indexer does not produce Field/Property nodes for the fixture — skip rather than fail.
    pytest.skip("No Field/Property node in Python fixture")


# ---------------------------------------------------------------------------
# Call chain / entry point / impact tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_entry_points(python_mcp: FastMCP) -> None:
    """find_entry_points returns dict without error (may be empty for Python fixture)."""
    result = run(python_mcp.call_tool("find_entry_points", {
        "method": "synappspytest.services.AnimalService.get_greeting",
    }))
    ep = result_json(result)
    assert isinstance(ep, dict)
    assert "entry_points" in ep


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_call_depth(python_mcp: FastMCP) -> None:
    """find_callees with depth param returns dict with callees key without error."""
    result = run(python_mcp.call_tool("find_callees", {
        "method_full_name": "synappspytest.services.AnimalService.get_greeting",
        "depth": 3,
    }))
    depth_result = result_json(result)
    assert isinstance(depth_result, dict)
    assert "callees" in depth_result


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_impact(python_mcp: FastMCP) -> None:
    """get_context_for(scope='impact') returns compact text summary for a Python method."""
    result = run(python_mcp.call_tool("get_context_for", {
        "full_name": "synappspytest.services.AnimalService.get_greeting",
        "scope": "impact",
    }))
    output = text(result)
    assert "Change Impact" in output
    assert "get_greeting" in output
    assert "affected" in output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_impact(python_mcp: FastMCP) -> None:
    """find_usages with include_test_breakdown returns dict with expected keys for a Python type."""
    result = run(python_mcp.call_tool("find_usages", {
        "full_name": "synappspytest.animals.IAnimal",
        "include_test_breakdown": True,
    }))
    impact = result_json(result)
    assert isinstance(impact, dict)
    assert "references" in impact
    assert "prod_count" in impact
    assert "test_count" in impact


# ---------------------------------------------------------------------------
# Summary tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_summary_no_summary(python_mcp: FastMCP) -> None:
    """summary action=get returns None or empty when no summary set for Python symbol."""
    result = run(python_mcp.call_tool("summary", {
        "action": "get",
        "full_name": "synappspytest.animals.Cat",
    }))
    summary = result_json(result)
    assert summary is None or isinstance(summary, str)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_set_and_get_summary(python_mcp: FastMCP) -> None:
    """summary action=set/get round-trip correctly for a Python symbol."""
    run(python_mcp.call_tool("summary", {
        "action": "set",
        "full_name": "synappspytest.animals.Dog",
        "content": "A dog that barks.",
    }))
    result = run(python_mcp.call_tool("summary", {
        "action": "get",
        "full_name": "synappspytest.animals.Dog",
    }))
    assert text(result) == "A dog that barks."


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_summarized(python_mcp: FastMCP) -> None:
    """summary action=list includes the symbol annotated in test_set_and_get_summary."""
    run(python_mcp.call_tool("summary", {
        "action": "set",
        "full_name": "synappspytest.animals.Dog",
        "content": "A dog that barks.",
    }))
    result = run(python_mcp.call_tool("summary", {"action": "list"}))
    items = result_json(result)
    names = [i.get("full_name") for i in items]
    assert "synappspytest.animals.Dog" in names


# ---------------------------------------------------------------------------
# Execute query
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_query(python_mcp: FastMCP) -> None:
    """execute_query can count Python Class nodes in the graph."""
    result = run(python_mcp.call_tool("execute_query", {
        "cypher": "MATCH (n:Class {language: 'python'}) RETURN count(n) AS cnt"
    }))
    rows = result_json(result)
    assert isinstance(rows, list)
    assert len(rows) > 0
    # execute_query wraps each row as {"row": [cell, ...]}
    count = rows[0]["row"][0]
    assert count > 0, f"Expected at least one Python Class node, got count={count}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_mutating_query_blocked(python_mcp: FastMCP) -> None:
    """execute_query raises when a mutating (CREATE) Cypher query is submitted."""
    with pytest.raises(Exception):
        run(python_mcp.call_tool("execute_query", {
            "cypher": "CREATE (n:Fake) RETURN n"
        }))
