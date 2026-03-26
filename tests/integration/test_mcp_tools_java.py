"""
MCP tool integration tests against the Java fixture (SynapseJavaTest).

Requires Memgraph on localhost:7687 and Eclipse JDT LS (Java JDK 11+).
Run with: pytest tests/integration/test_mcp_tools_java.py -v -m integration

NOTE: GraphHopper (/Users/alex/Dev/opensource/graphhopper) can be used for
real-world validation per D-22, but is NOT included in CI tests (too large/slow).
"""
from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP

from tests.integration.conftest import run, text, result_json, JAVA_FIXTURE_PATH


# ---------------------------------------------------------------------------
# Project-level tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_projects(java_mcp: FastMCP) -> None:
    """list_projects returns at least one project with language 'java'."""
    result = run(java_mcp.call_tool("list_projects", {}))
    projects = result_json(result)
    assert isinstance(projects, list)
    assert len(projects) >= 1
    all_languages = [lang for p in projects for lang in p.get("languages", [])]
    assert "java" in all_languages, f"Expected 'java' in project languages, got: {all_languages}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_index_status(java_mcp: FastMCP) -> None:
    """list_projects(path=...) returns a populated status dict for the Java fixture."""
    result = run(java_mcp.call_tool("list_projects", {"path": JAVA_FIXTURE_PATH}))
    status = result_json(result)
    assert status is not None
    assert status["file_count"] > 0
    assert status["symbol_count"] > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_schema(java_mcp: FastMCP) -> None:
    """get_schema returns the graph schema (not Java-specific, but must not error)."""
    result = run(java_mcp.call_tool("get_schema", {}))
    schema = result_json(result)
    assert "node_labels" in schema


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_index_project(java_mcp: FastMCP) -> None:
    """index_project re-indexes the Java fixture without error (upsert -- safe to re-run)."""
    result = run(java_mcp.call_tool("index_project", {
        "path": JAVA_FIXTURE_PATH,
        "language": "java",
    }))
    msg = text(result)
    assert "Indexed" in msg



# ---------------------------------------------------------------------------
# Symbol query tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol(java_mcp: FastMCP) -> None:
    """get_symbol returns a node for a known Java interface."""
    result = run(java_mcp.call_tool("get_symbol", {
        "full_name": "com.synapsetest.IAnimal"
    }))
    symbol = result_json(result)
    assert symbol is not None
    assert "IAnimal" in symbol["full_name"]


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_is_abstract(java_mcp: FastMCP) -> None:
    """get_symbol on an abstract class returns is_abstract=True."""
    result = run(java_mcp.call_tool("get_symbol", {
        "full_name": "com.synapsetest.Animal"
    }))
    symbol = result_json(result)
    assert symbol is not None
    assert symbol.get("is_abstract") is True, (
        f"Expected is_abstract=True for Animal, got: {symbol.get('is_abstract')}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_source(java_mcp: FastMCP) -> None:
    """get_symbol_source returns Java source code for a known class."""
    result = run(java_mcp.call_tool("get_symbol_source", {
        "full_name": "com.synapsetest.Dog"
    }))
    source = text(result)
    assert isinstance(source, str)
    assert len(source) > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols_finds_classes(java_mcp: FastMCP) -> None:
    """search_symbols for 'Animal' returns Animal and IAnimal."""
    result = run(java_mcp.call_tool("search_symbols", {"query": "Animal"}))
    symbols = result_json(result)
    assert isinstance(symbols, list)
    assert len(symbols) >= 2
    names = [s["full_name"] for s in symbols]
    assert any("Animal" in n for n in names)
    assert any("IAnimal" in n for n in names), f"Expected IAnimal in {names}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols_by_kind(java_mcp: FastMCP) -> None:
    """search_symbols with kind='interface' finds IAnimal."""
    result = run(java_mcp.call_tool("search_symbols", {
        "query": "Animal",
        "kind": "interface",
    }))
    symbols = result_json(result)
    assert isinstance(symbols, list)
    assert len(symbols) >= 1
    names = [s["full_name"] for s in symbols]
    assert any("IAnimal" in n for n in names), f"Expected IAnimal in {names}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols_language_filter(java_mcp: FastMCP) -> None:
    """search_symbols with language='java' returns only Java symbols."""
    result = run(java_mcp.call_tool("search_symbols", {
        "query": "Animal",
        "language": "java",
    }))
    symbols = result_json(result)
    assert isinstance(symbols, list)
    for sym in symbols:
        assert sym.get("language") == "java", (
            f"Expected language='java', got: {sym.get('language')} for {sym.get('full_name')}"
        )


# ---------------------------------------------------------------------------
# Relationship tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_implementations(java_mcp: FastMCP) -> None:
    """find_implementations for IAnimal returns its implementing classes."""
    result = run(java_mcp.call_tool("find_implementations", {
        "interface_name": "com.synapsetest.IAnimal"
    }))
    impls = result_json(result)
    assert isinstance(impls, list)
    assert len(impls) >= 1, f"Expected at least Animal implementing IAnimal, got {impls}"
    names = [i.get("full_name", "") for i in impls]
    assert any("Animal" in n for n in names), f"Expected Animal in {names}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_hierarchy(java_mcp: FastMCP) -> None:
    """get_hierarchy for Dog returns Animal in parent chain."""
    result = run(java_mcp.call_tool("get_hierarchy", {
        "class_name": "com.synapsetest.Dog"
    }))
    hierarchy = result_json(result)
    assert "parents" in hierarchy
    parent_names = [p.get("full_name", "") for p in hierarchy["parents"]]
    assert any("Animal" in n for n in parent_names), (
        f"Expected Animal in Dog's parents, got: {parent_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callers(java_mcp: FastMCP) -> None:
    """find_callers returns a list (possibly empty) without error for Java method."""
    result = run(java_mcp.call_tool("find_callers", {
        "method_full_name": "com.synapsetest.IAnimal.speak"
    }))
    callers = result_json(result)
    assert isinstance(callers, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callees(java_mcp: FastMCP) -> None:
    """find_callees returns a list (possibly empty) without error for Java method."""
    result = run(java_mcp.call_tool("find_callees", {
        "method_full_name": "com.synapsetest.AnimalService.greet"
    }))
    callees = result_json(result)
    assert isinstance(callees, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_references(java_mcp: FastMCP) -> None:
    """find_usages with kind='parameter' returns list (possibly empty) without error for Java interface."""
    result = run(java_mcp.call_tool("find_usages", {
        "full_name": "com.synapsetest.IAnimal",
        "kind": "parameter",
    }))
    refs = result_json(result)
    assert isinstance(refs, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_usages(java_mcp: FastMCP) -> None:
    """find_usages returns compact text summary for a Java interface."""
    result = run(java_mcp.call_tool("find_usages", {
        "full_name": "com.synapsetest.IAnimal"
    }))
    output = text(result)
    assert "Usages of" in output
    assert "IAnimal" in output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_dependencies(java_mcp: FastMCP) -> None:
    """find_dependencies returns list without error for AnimalService."""
    result = run(java_mcp.call_tool("find_dependencies", {
        "full_name": "com.synapsetest.AnimalService"
    }))
    deps = result_json(result)
    assert isinstance(deps, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for(java_mcp: FastMCP) -> None:
    """get_context_for returns context string for a Java class."""
    result = run(java_mcp.call_tool("get_context_for", {
        "full_name": "com.synapsetest.Dog"
    }))
    ctx = text(result)
    assert len(ctx) > 0
    assert "Dog" in ctx



# ---------------------------------------------------------------------------
# Call chain / entry point / impact tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_trace_call_chain(java_mcp: FastMCP) -> None:
    """trace_call_chain returns dict with paths key (may be empty for Java fixture)."""
    result = run(java_mcp.call_tool("trace_call_chain", {
        "start": "com.synapsetest.AnimalService.greet",
        "end": "com.synapsetest.IAnimal.speak",
    }))
    trace = result_json(result)
    assert isinstance(trace, dict)
    assert "paths" in trace


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_entry_points(java_mcp: FastMCP) -> None:
    """find_entry_points returns dict with entry_points key without error."""
    result = run(java_mcp.call_tool("find_entry_points", {
        "method": "com.synapsetest.AnimalService.greet",
    }))
    ep = result_json(result)
    assert isinstance(ep, dict)
    assert "entry_points" in ep


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_call_depth(java_mcp: FastMCP) -> None:
    """find_callees with depth param returns dict with callees key without error."""
    result = run(java_mcp.call_tool("find_callees", {
        "method_full_name": "com.synapsetest.AnimalService.greet",
        "depth": 3,
    }))
    depth_result = result_json(result)
    assert isinstance(depth_result, dict)
    assert "callees" in depth_result


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_analyze_change_impact(java_mcp: FastMCP) -> None:
    """analyze_change_impact returns compact text summary for a Java method."""
    result = run(java_mcp.call_tool("analyze_change_impact", {
        "method": "com.synapsetest.AnimalService.greet"
    }))
    output = text(result)
    assert "Change Impact" in output
    assert "greet" in output
    assert "affected" in output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_impact(java_mcp: FastMCP) -> None:
    """find_usages with include_test_breakdown returns dict with expected keys for a Java type."""
    result = run(java_mcp.call_tool("find_usages", {
        "full_name": "com.synapsetest.IAnimal",
        "include_test_breakdown": True,
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
def test_summarize_from_graph(java_mcp: FastMCP) -> None:
    """summarize_from_graph returns a summary dict for a Java class."""
    result = run(java_mcp.call_tool("summarize_from_graph", {
        "class_name": "com.synapsetest.Dog",
    }))
    summary = result_json(result)
    assert summary is not None
    assert "summary" in summary


# ---------------------------------------------------------------------------
# Summary tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_set_and_get_summary(java_mcp: FastMCP) -> None:
    """summary action=set/get round-trip correctly for a Java symbol."""
    run(java_mcp.call_tool("summary", {
        "action": "set",
        "full_name": "com.synapsetest.Dog",
        "content": "A dog class that barks.",
    }))
    result = run(java_mcp.call_tool("summary", {
        "action": "get",
        "full_name": "com.synapsetest.Dog",
    }))
    assert text(result) == "A dog class that barks."


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_summarized(java_mcp: FastMCP) -> None:
    """summary action=list includes the symbol annotated in test_set_and_get_summary."""
    run(java_mcp.call_tool("summary", {
        "action": "set",
        "full_name": "com.synapsetest.Dog",
        "content": "A dog class that barks.",
    }))
    result = run(java_mcp.call_tool("summary", {"action": "list"}))
    items = result_json(result)
    names = [i.get("full_name") for i in items]
    assert "com.synapsetest.Dog" in names


# ---------------------------------------------------------------------------
# Execute query
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_query(java_mcp: FastMCP) -> None:
    """execute_query can count Java Class nodes in the graph."""
    result = run(java_mcp.call_tool("execute_query", {
        "cypher": "MATCH (n:Class {language: 'java'}) RETURN count(n) AS cnt"
    }))
    rows = result_json(result)
    assert isinstance(rows, list)
    assert len(rows) > 0
    count = rows[0]["row"][0]
    assert count > 0, f"Expected at least one Java Class node, got count={count}"
