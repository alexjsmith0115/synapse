"""
MCP tool integration tests against the Python fixture (SynapsePyTest).

Requires Memgraph on localhost:7687 and Python indexer.
Run with: pytest tests/integration/test_mcp_tools_python.py -v -m integration
"""
from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP

from synapse.service import SynapseService
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
    """get_index_status returns a populated status dict for the Python fixture."""
    result = run(python_mcp.call_tool("get_index_status", {"path": PYTHON_FIXTURE_PATH}))
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


# ---------------------------------------------------------------------------
# Symbol query tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol(python_mcp: FastMCP) -> None:
    """get_symbol returns a node for a known Python class."""
    result = run(python_mcp.call_tool("get_symbol", {
        "full_name": "synapsepytest.animals.IAnimal"
    }))
    symbol = result_json(result)
    assert symbol is not None
    assert "IAnimal" in symbol["full_name"]


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_is_abstract(python_mcp: FastMCP) -> None:
    """get_symbol on an ABC class returns is_abstract=True."""
    result = run(python_mcp.call_tool("get_symbol", {
        "full_name": "synapsepytest.animals.IAnimal"
    }))
    symbol = result_json(result)
    assert symbol is not None
    assert symbol.get("is_abstract") is True, (
        f"Expected is_abstract=True for IAnimal, got: {symbol.get('is_abstract')}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_metadata_static(python_mcp: FastMCP) -> None:
    """get_symbol on a @staticmethod returns is_static=True."""
    result = run(python_mcp.call_tool("get_symbol", {
        "full_name": "synapsepytest.services.AnimalService.version"
    }))
    symbol = result_json(result)
    assert symbol is not None
    assert symbol.get("is_static") is True, (
        f"Expected is_static=True for AnimalService.version, got: {symbol.get('is_static')}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_metadata_classmethod(python_mcp: FastMCP) -> None:
    """get_symbol on a @classmethod returns is_classmethod=True."""
    result = run(python_mcp.call_tool("get_symbol", {
        "full_name": "synapsepytest.services.AnimalService.from_name"
    }))
    symbol = result_json(result)
    assert symbol is not None
    assert symbol.get("is_classmethod") is True, (
        f"Expected is_classmethod=True for AnimalService.from_name, got: {symbol.get('is_classmethod')}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_metadata_async(python_mcp: FastMCP) -> None:
    """get_symbol on an async def returns is_async=True."""
    result = run(python_mcp.call_tool("get_symbol", {
        "full_name": "synapsepytest.services.AnimalService.get_greeting_async"
    }))
    symbol = result_json(result)
    assert symbol is not None
    assert symbol.get("is_async") is True, (
        f"Expected is_async=True for AnimalService.get_greeting_async, got: {symbol.get('is_async')}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_source(python_mcp: FastMCP) -> None:
    """get_symbol_source returns Python source code for a known method."""
    result = run(python_mcp.call_tool("get_symbol_source", {
        "full_name": "synapsepytest.animals.Dog.speak"
    }))
    source = text(result)
    assert source is not None
    assert len(source) > 0


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
        "interface_name": "synapsepytest.animals.IAnimal"
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
        "class_name": "synapsepytest.animals.Dog"
    }))
    hierarchy = result_json(result)
    assert "parents" in hierarchy
    parent_names = [p.get("full_name", "") for p in hierarchy["parents"]]
    assert any("Animal" in n for n in parent_names), (
        f"Expected Animal in Dog's parents, got: {parent_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callers(python_mcp: FastMCP) -> None:
    """find_callers returns callers (possibly empty for Python fixture) without error."""
    result = run(python_mcp.call_tool("find_callers", {
        "method_full_name": "synapsepytest.animals.IAnimal.speak"
    }))
    callers = result_json(result)
    assert isinstance(callers, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callees(python_mcp: FastMCP) -> None:
    """find_callees returns callees (possibly empty for Python fixture) without error."""
    result = run(python_mcp.call_tool("find_callees", {
        "method_full_name": "synapsepytest.services.AnimalService.get_greeting"
    }))
    callees = result_json(result)
    assert isinstance(callees, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_references(python_mcp: FastMCP) -> None:
    """find_type_references returns list (possibly empty for Python) without error."""
    result = run(python_mcp.call_tool("find_type_references", {
        "full_name": "synapsepytest.animals.IAnimal"
    }))
    refs = result_json(result)
    assert isinstance(refs, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_usages(python_mcp: FastMCP) -> None:
    """find_usages returns compact text summary for a Python class."""
    result = run(python_mcp.call_tool("find_usages", {
        "full_name": "synapsepytest.animals.IAnimal"
    }))
    output = text(result)
    assert "Usages of" in output
    assert "IAnimal" in output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_dependencies(python_mcp: FastMCP) -> None:
    """find_dependencies returns list without error for AnimalService."""
    result = run(python_mcp.call_tool("find_dependencies", {
        "full_name": "synapsepytest.services.AnimalService"
    }))
    deps = result_json(result)
    assert isinstance(deps, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for(python_mcp: FastMCP) -> None:
    """get_context_for returns context string for a Python class."""
    result = run(python_mcp.call_tool("get_context_for", {
        "full_name": "synapsepytest.animals.Dog"
    }))
    ctx = text(result)
    assert len(ctx) > 0
    assert "Dog" in ctx


# ---------------------------------------------------------------------------
# Call chain / entry point / impact tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_trace_call_chain(python_mcp: FastMCP) -> None:
    """trace_call_chain returns dict with paths key without error (may be empty for Python)."""
    result = run(python_mcp.call_tool("trace_call_chain", {
        "start": "synapsepytest.services.AnimalService.get_greeting",
        "end": "synapsepytest.animals.IAnimal.speak",
    }))
    trace = result_json(result)
    assert isinstance(trace, dict)
    assert "paths" in trace


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_entry_points(python_mcp: FastMCP) -> None:
    """find_entry_points returns dict without error (may be empty for Python fixture)."""
    result = run(python_mcp.call_tool("find_entry_points", {
        "method": "synapsepytest.services.AnimalService.get_greeting",
    }))
    ep = result_json(result)
    assert isinstance(ep, dict)
    assert "entry_points" in ep


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_call_depth(python_mcp: FastMCP) -> None:
    """get_call_depth returns dict with callees key without error."""
    result = run(python_mcp.call_tool("get_call_depth", {
        "method": "synapsepytest.services.AnimalService.get_greeting",
        "depth": 3,
    }))
    depth_result = result_json(result)
    assert isinstance(depth_result, dict)
    assert "callees" in depth_result


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_analyze_change_impact(python_mcp: FastMCP) -> None:
    """analyze_change_impact returns compact text summary for a Python method."""
    result = run(python_mcp.call_tool("analyze_change_impact", {
        "method": "synapsepytest.services.AnimalService.get_greeting",
    }))
    output = text(result)
    assert "Change Impact" in output
    assert "get_greeting" in output
    assert "affected" in output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_interface_contract(python_mcp: FastMCP) -> None:
    """find_interface_contract returns dict without error (may be empty for Python)."""
    result = run(python_mcp.call_tool("find_interface_contract", {
        "method": "synapsepytest.services.AnimalService.get_greeting",
    }))
    contract = result_json(result)
    assert isinstance(contract, dict)
    assert "interface" in contract


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_impact(python_mcp: FastMCP) -> None:
    """find_type_impact returns dict with expected keys for a Python type."""
    result = run(python_mcp.call_tool("find_type_impact", {
        "type_name": "synapsepytest.animals.IAnimal"
    }))
    impact = result_json(result)
    assert isinstance(impact, dict)
    assert "references" in impact
    assert "prod_count" in impact
    assert "test_count" in impact


# ---------------------------------------------------------------------------
# Audit / summarize tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_audit_architecture(python_mcp: FastMCP) -> None:
    """audit_architecture runs without error (empty violations for Python is OK)."""
    result = run(python_mcp.call_tool("audit_architecture", {
        "rule": "layering_violations",
    }))
    audit = result_json(result)
    assert isinstance(audit, dict)
    assert "violations" in audit
    assert "count" in audit


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_summarize_from_graph(python_mcp: FastMCP) -> None:
    """summarize_from_graph returns a summary dict for a Python class."""
    result = run(python_mcp.call_tool("summarize_from_graph", {
        "class_name": "synapsepytest.animals.Dog",
    }))
    summary = result_json(result)
    assert summary is not None
    assert "summary" in summary


# ---------------------------------------------------------------------------
# Summary tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_set_and_get_summary(python_mcp: FastMCP) -> None:
    """set_summary and get_summary round-trip correctly for a Python symbol."""
    run(python_mcp.call_tool("set_summary", {
        "full_name": "synapsepytest.animals.Dog",
        "content": "A dog that barks.",
    }))
    result = run(python_mcp.call_tool("get_summary", {
        "full_name": "synapsepytest.animals.Dog"
    }))
    assert text(result) == "A dog that barks."


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_summarized(python_mcp: FastMCP) -> None:
    """list_summarized includes the symbol annotated in test_set_and_get_summary."""
    run(python_mcp.call_tool("set_summary", {
        "full_name": "synapsepytest.animals.Dog",
        "content": "A dog that barks.",
    }))
    result = run(python_mcp.call_tool("list_summarized", {}))
    items = result_json(result)
    names = [i.get("full_name") for i in items]
    assert "synapsepytest.animals.Dog" in names


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
