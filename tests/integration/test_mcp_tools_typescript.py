"""
MCP tool integration tests against the TypeScript fixture (SynapseJSTest).

Requires Memgraph on localhost:7687 and tsserver (TypeScript Language Server).
Run with: pytest tests/integration/test_mcp_tools_typescript.py -v -m integration
"""
from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP

from synapse.service import SynapseService
from tests.integration.conftest import run, text, result_json, TYPESCRIPT_FIXTURE_PATH


# ---------------------------------------------------------------------------
# Project-level tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_projects(typescript_mcp: FastMCP) -> None:
    """list_projects returns at least one project with language 'typescript'."""
    result = run(typescript_mcp.call_tool("list_projects", {}))
    projects = result_json(result)
    assert isinstance(projects, list)
    assert len(projects) >= 1
    all_languages = [lang for p in projects for lang in p.get("languages", [])]
    assert "typescript" in all_languages, f"Expected 'typescript' in project languages, got: {all_languages}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_index_status(typescript_mcp: FastMCP) -> None:
    """get_index_status returns a populated status dict for the TypeScript fixture."""
    result = run(typescript_mcp.call_tool("get_index_status", {"path": TYPESCRIPT_FIXTURE_PATH}))
    status = result_json(result)
    assert status is not None
    assert status["file_count"] > 0
    assert status["symbol_count"] > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_schema(typescript_mcp: FastMCP) -> None:
    """get_schema returns the graph schema (not TypeScript-specific, but must not error)."""
    result = run(typescript_mcp.call_tool("get_schema", {}))
    schema = result_json(result)
    assert "node_labels" in schema


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_index_project(typescript_mcp: FastMCP) -> None:
    """index_project re-indexes the TypeScript fixture without error (upsert — safe to re-run)."""
    result = run(typescript_mcp.call_tool("index_project", {
        "path": TYPESCRIPT_FIXTURE_PATH,
        "language": "typescript",
    }))
    msg = text(result)
    assert "Indexed" in msg


@pytest.mark.integration
@pytest.mark.timeout(60)
def test_delete_project(typescript_mcp: FastMCP, typescript_service: SynapseService) -> None:
    """delete_project removes the TypeScript project; re-index restores it for downstream tests."""
    result = run(typescript_mcp.call_tool("delete_project", {
        "path": TYPESCRIPT_FIXTURE_PATH,
    }))
    msg = text(result)
    assert "Deleted" in msg

    # Restore the graph so session fixtures remain valid for all other tests.
    typescript_service.index_project(TYPESCRIPT_FIXTURE_PATH, "typescript")


# ---------------------------------------------------------------------------
# Symbol query tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol(typescript_mcp: FastMCP) -> None:
    """get_symbol returns a node for a known TypeScript interface."""
    result = run(typescript_mcp.call_tool("get_symbol", {
        "full_name": "src/animals.IAnimal"
    }))
    symbol = result_json(result)
    assert symbol is not None
    assert "IAnimal" in symbol["full_name"]


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_is_abstract(typescript_mcp: FastMCP) -> None:
    """get_symbol on an abstract class returns is_abstract=True."""
    result = run(typescript_mcp.call_tool("get_symbol", {
        "full_name": "src/animals.Animal"
    }))
    symbol = result_json(result)
    assert symbol is not None
    assert symbol.get("is_abstract") is True, (
        f"Expected is_abstract=True for Animal, got: {symbol.get('is_abstract')}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_source(typescript_mcp: FastMCP) -> None:
    """get_symbol_source returns source or not-found message for a TypeScript class."""
    result = run(typescript_mcp.call_tool("get_symbol_source", {
        "full_name": "src/animals.Dog"
    }))
    source = text(result)
    # Source retrieval depends on LSP; assert it's a non-empty string (source or message)
    assert isinstance(source, str)
    assert len(source) > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols(typescript_mcp: FastMCP) -> None:
    """search_symbols returns matching TypeScript symbols."""
    result = run(typescript_mcp.call_tool("search_symbols", {"query": "Dog"}))
    symbols = result_json(result)
    assert isinstance(symbols, list)
    assert len(symbols) >= 1
    names = [s["full_name"] for s in symbols]
    assert any("Dog" in n for n in names), f"Expected 'Dog' in symbol names, got: {names}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols_language_filter(typescript_mcp: FastMCP) -> None:
    """search_symbols with language='typescript' returns only TypeScript symbols."""
    result = run(typescript_mcp.call_tool("search_symbols", {
        "query": "Animal",
        "language": "typescript",
    }))
    symbols = result_json(result)
    assert isinstance(symbols, list)
    for sym in symbols:
        assert sym.get("language") == "typescript", (
            f"Expected language='typescript', got: {sym.get('language')} for {sym.get('full_name')}"
        )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_related_symbols(typescript_mcp: FastMCP) -> None:
    """find_type_references returns a list (possibly empty) for a TypeScript class."""
    result = run(typescript_mcp.call_tool("find_type_references", {
        "full_name": "src/animals.Dog"
    }))
    refs = result_json(result)
    assert isinstance(refs, list)


# ---------------------------------------------------------------------------
# Hierarchy tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_hierarchy(typescript_mcp: FastMCP) -> None:
    """get_hierarchy for Dog returns Animal in parent chain."""
    result = run(typescript_mcp.call_tool("get_hierarchy", {
        "class_name": "src/animals.Dog"
    }))
    hierarchy = result_json(result)
    assert "parents" in hierarchy
    parent_names = [p.get("full_name", "") for p in hierarchy["parents"]]
    assert any("Animal" in n for n in parent_names), (
        f"Expected Animal in Dog's parents, got: {parent_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_implementations(typescript_mcp: FastMCP) -> None:
    """find_implementations for IAnimal returns its subclasses."""
    result = run(typescript_mcp.call_tool("find_implementations", {
        "interface_name": "src/animals.IAnimal"
    }))
    impls = result_json(result)
    assert isinstance(impls, list)
    assert len(impls) >= 1, f"Expected at least one implementation of IAnimal, got {impls}"
    names = [i.get("full_name", "") for i in impls]
    assert any("Animal" in n for n in names), f"Expected Animal (or subclass) in {names}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_interface_contract(typescript_mcp: FastMCP) -> None:
    """find_interface_contract returns a dict with interface key for a TypeScript method."""
    result = run(typescript_mcp.call_tool("find_interface_contract", {
        "method": "src/animals.Dog.speak"
    }))
    contract = result_json(result)
    assert isinstance(contract, dict)
    assert "interface" in contract


# ---------------------------------------------------------------------------
# Call graph tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callers(typescript_mcp: FastMCP) -> None:
    """find_callers returns a list (possibly empty) without error for TypeScript method."""
    result = run(typescript_mcp.call_tool("find_callers", {
        "method_full_name": "src/services.AnimalService.getGreeting"
    }))
    callers = result_json(result)
    # Call edges depend on tsserver availability — assert list type only
    assert isinstance(callers, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callees(typescript_mcp: FastMCP) -> None:
    """find_callees returns a list (possibly empty) without error for TypeScript method."""
    result = run(typescript_mcp.call_tool("find_callees", {
        "method_full_name": "src/services.Greeter.greet"
    }))
    callees = result_json(result)
    assert isinstance(callees, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_call_depth(typescript_mcp: FastMCP) -> None:
    """get_call_depth returns dict with callees key for a TypeScript method."""
    result = run(typescript_mcp.call_tool("get_call_depth", {
        "method": "src/services.Greeter.greet",
        "depth": 3,
    }))
    depth_result = result_json(result)
    assert isinstance(depth_result, dict)
    assert "callees" in depth_result


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_trace_call_chain(typescript_mcp: FastMCP) -> None:
    """trace_call_chain returns dict with paths key (may be empty) for TypeScript methods."""
    result = run(typescript_mcp.call_tool("trace_call_chain", {
        "start": "src/services.Greeter.greet",
        "end": "src/animals.IAnimal.speak",
    }))
    trace = result_json(result)
    assert isinstance(trace, dict)
    assert "paths" in trace


# ---------------------------------------------------------------------------
# Dependency tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_dependencies(typescript_mcp: FastMCP) -> None:
    """find_dependencies returns a list for a TypeScript class."""
    result = run(typescript_mcp.call_tool("find_dependencies", {
        "full_name": "src/services.AnimalService"
    }))
    deps = result_json(result)
    assert isinstance(deps, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_references(typescript_mcp: FastMCP) -> None:
    """find_type_references returns list (possibly empty) without error for TypeScript interface."""
    result = run(typescript_mcp.call_tool("find_type_references", {
        "full_name": "src/animals.IAnimal"
    }))
    refs = result_json(result)
    assert isinstance(refs, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_usages(typescript_mcp: FastMCP) -> None:
    """find_usages returns compact text summary for a TypeScript interface."""
    result = run(typescript_mcp.call_tool("find_usages", {
        "full_name": "src/animals.IAnimal"
    }))
    output = text(result)
    assert "Usages of" in output
    assert "IAnimal" in output


# ---------------------------------------------------------------------------
# Analysis tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_analyze_change_impact(typescript_mcp: FastMCP) -> None:
    """analyze_change_impact returns compact text summary for a TypeScript method."""
    result = run(typescript_mcp.call_tool("analyze_change_impact", {
        "method": "src/services.AnimalService.getGreeting"
    }))
    output = text(result)
    assert "Change Impact" in output
    assert "getGreeting" in output
    assert "affected" in output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for(typescript_mcp: FastMCP) -> None:
    """get_context_for returns non-empty context string for a TypeScript class."""
    result = run(typescript_mcp.call_tool("get_context_for", {
        "full_name": "src/animals.Dog"
    }))
    ctx = text(result)
    assert len(ctx) > 0
    assert "Dog" in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_entry_points(typescript_mcp: FastMCP) -> None:
    """find_entry_points returns dict with entry_points key without error."""
    result = run(typescript_mcp.call_tool("find_entry_points", {
        "method": "src/services.AnimalService.getGreeting",
    }))
    ep = result_json(result)
    assert isinstance(ep, dict)
    assert "entry_points" in ep


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_impact(typescript_mcp: FastMCP) -> None:
    """find_type_impact returns dict with expected keys for a TypeScript type."""
    result = run(typescript_mcp.call_tool("find_type_impact", {
        "type_name": "src/animals.IAnimal"
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
def test_get_summary_no_summary(typescript_mcp: FastMCP) -> None:
    """get_summary returns None or empty when no summary set for TypeScript symbol."""
    result = run(typescript_mcp.call_tool("get_summary", {
        "full_name": "src/animals.Cat"
    }))
    summary = result_json(result)
    # No summary set yet — should be None
    assert summary is None or isinstance(summary, str)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_set_and_get_summary(typescript_mcp: FastMCP) -> None:
    """set_summary and get_summary round-trip correctly for a TypeScript symbol."""
    run(typescript_mcp.call_tool("set_summary", {
        "full_name": "src/animals.Dog",
        "content": "A dog class in TypeScript.",
    }))
    result = run(typescript_mcp.call_tool("get_summary", {
        "full_name": "src/animals.Dog"
    }))
    assert text(result) == "A dog class in TypeScript."


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_summarized(typescript_mcp: FastMCP) -> None:
    """list_summarized includes the symbol annotated in test_set_and_get_summary."""
    run(typescript_mcp.call_tool("set_summary", {
        "full_name": "src/animals.Dog",
        "content": "A dog class in TypeScript.",
    }))
    result = run(typescript_mcp.call_tool("list_summarized", {}))
    items = result_json(result)
    names = [i.get("full_name") for i in items]
    assert "src/animals.Dog" in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_summarize_from_graph(typescript_mcp: FastMCP) -> None:
    """summarize_from_graph returns a summary dict for a TypeScript class."""
    result = run(typescript_mcp.call_tool("summarize_from_graph", {
        "class_name": "src/animals.Dog",
    }))
    summary = result_json(result)
    assert summary is not None
    assert "summary" in summary


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_audit_architecture(typescript_mcp: FastMCP) -> None:
    """audit_architecture runs without error (empty violations for TypeScript is OK)."""
    result = run(typescript_mcp.call_tool("audit_architecture", {
        "rule": "layering_violations",
    }))
    audit = result_json(result)
    assert isinstance(audit, dict)
    assert "violations" in audit
    assert "count" in audit


# ---------------------------------------------------------------------------
# Execute query
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_query(typescript_mcp: FastMCP) -> None:
    """execute_query can count TypeScript Class nodes in the graph."""
    result = run(typescript_mcp.call_tool("execute_query", {
        "cypher": "MATCH (n:Class {language: 'typescript'}) RETURN count(n) AS cnt"
    }))
    rows = result_json(result)
    assert isinstance(rows, list)
    assert len(rows) > 0
    # execute_query wraps each row as {"row": [cell, ...]}
    count = rows[0]["row"][0]
    assert count > 0, f"Expected at least one TypeScript Class node, got count={count}"
