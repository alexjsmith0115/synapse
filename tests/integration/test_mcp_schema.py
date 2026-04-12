"""
MCP response schema validation tests.

Tests MCP-layer response shapes via call_tool() against live Memgraph with indexed
C# fixtures. Asserts structural shape (required keys + value types) on responses.

index_project and sync_project schema coverage provided by test_mcp_tools.py.

Run with: pytest tests/integration/test_mcp_schema.py -v -m integration
"""
from __future__ import annotations

import pytest
from typing import get_type_hints

from tests.integration.conftest import run, result_json, text, FIXTURE_PATH
from fixtures.contract_fixtures import (
    SearchSymbolsResult,
    FindCalleesResult,
    FindImplementationsResult,
    GetCallDepthResult,
    GetArchitectureOverviewResult,
    FindDeadCodeResult,
    FindUntestedResult,
    FindTypeReferencesResult,
)


def _assert_conforms(result: dict, shape: type, *, context: str = "") -> None:
    """Assert that result has all required keys of shape with correct types.

    Structural assertion only — does not check exact values.
    Uses __required_keys__ to distinguish required from optional fields.
    """
    hints = get_type_hints(shape)
    required = shape.__required_keys__
    prefix = f"[{context}] " if context else ""
    for key in required:
        assert key in result, f"{prefix}Missing required key {key!r}"
    for key, expected in hints.items():
        if key not in result:
            continue
        check = getattr(expected, "__origin__", expected)
        assert isinstance(result[key], check), (
            f"{prefix}Key {key!r}: expected {check.__name__}, got {type(result[key]).__name__}"
        )


# ---------------------------------------------------------------------------
# Structured-output tool shape tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_projects_no_path_envelope(mcp_server) -> None:
    result = run(mcp_server.call_tool("list_projects", {}))
    data = result_json(result)
    assert isinstance(data, dict)
    assert "synapps_mcp_version" in data
    assert isinstance(data["synapps_mcp_version"], str)
    assert "projects" in data
    assert isinstance(data["projects"], list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_projects_with_path_shape(mcp_server) -> None:
    result = run(mcp_server.call_tool("list_projects", {"path": FIXTURE_PATH}))
    data = result_json(result)
    assert isinstance(data, dict)
    assert "synapps_mcp_version" in data
    assert isinstance(data["synapps_mcp_version"], str)
    assert "path" in data
    assert isinstance(data["path"], str)
    assert "file_count" in data
    assert isinstance(data["file_count"], int)
    assert "symbol_count" in data
    assert isinstance(data["symbol_count"], int)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols_shape(mcp_server) -> None:
    result = run(mcp_server.call_tool("search_symbols", {"query": "TaskService", "kind": "Class"}))
    items = result_json(result)
    assert isinstance(items, list) and items
    _assert_conforms(items[0], SearchSymbolsResult, context="search_symbols")


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_implementations_shape(mcp_server) -> None:
    result = run(mcp_server.call_tool("find_implementations", {"full_name": "SynappsTest.Services.ITaskService"}))
    items = result_json(result)
    assert isinstance(items, list) and items
    _assert_conforms(items[0], FindImplementationsResult)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callees_shape(mcp_server) -> None:
    result = run(mcp_server.call_tool("find_callees", {"full_name": "SynappsTest.Controllers.TaskController.Create"}))
    items = result_json(result)
    assert isinstance(items, list) and items
    _assert_conforms(items[0], FindCalleesResult)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callees_depth_shape(mcp_server) -> None:
    result = run(mcp_server.call_tool("find_callees", {
        "full_name": "SynappsTest.Controllers.TaskController.Create",
        "depth": 2,
    }))
    data = result_json(result)
    _assert_conforms(data, GetCallDepthResult)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_schema_shape(mcp_server) -> None:
    result = run(mcp_server.call_tool("get_schema", {}))
    data = result_json(result)
    assert isinstance(data, dict)
    assert "node_labels" in data
    assert isinstance(data["node_labels"], dict)
    assert "relationship_types" in data
    assert isinstance(data["relationship_types"], dict)
    assert "notes" in data
    assert isinstance(data["notes"], list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_query_shape(mcp_server) -> None:
    result = run(mcp_server.call_tool("execute_query", {"cypher": "MATCH (n:Class) RETURN n.name LIMIT 1"}))
    assert isinstance(result_json(result), list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_usages_with_kind_shape(mcp_server) -> None:
    result = run(mcp_server.call_tool("find_usages", {
        "full_name": "SynappsTest.Services.ITaskService",
        "kind": "parameter",
    }))
    items = result_json(result)
    assert isinstance(items, list) and items
    _assert_conforms(items[0], FindTypeReferencesResult, context="find_usages")


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_architecture_shape(mcp_server) -> None:
    result = run(mcp_server.call_tool("get_architecture", {"path": FIXTURE_PATH}))
    _assert_conforms(result_json(result), GetArchitectureOverviewResult)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_dead_code_shape(mcp_server) -> None:
    result = run(mcp_server.call_tool("find_dead_code", {"path": FIXTURE_PATH}))
    _assert_conforms(result_json(result), FindDeadCodeResult)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_untested_shape(mcp_server) -> None:
    result = run(mcp_server.call_tool("find_untested", {"path": FIXTURE_PATH}))
    _assert_conforms(result_json(result), FindUntestedResult)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_summary_list_shape(mcp_server) -> None:
    result = run(mcp_server.call_tool("summary", {"action": "list"}))
    data = result_json(result)
    if data is not None:
        assert isinstance(data, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_http_endpoints(mcp_server) -> None:
    result = run(mcp_server.call_tool("find_http_endpoints", {}))
    assert isinstance(result_json(result), list)


# ---------------------------------------------------------------------------
# Text-output tool shape tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_read_symbol_returns_str(mcp_server) -> None:
    result = run(mcp_server.call_tool("read_symbol", {"full_name": "SynappsTest.Services.TaskService.CreateTaskAsync"}))
    assert isinstance(text(result), str)
    assert len(text(result)) > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_returns_str(mcp_server) -> None:
    result = run(mcp_server.call_tool("get_context_for", {"full_name": "SynappsTest.Controllers.TaskController"}))
    assert isinstance(text(result), str)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_assess_impact_returns_str(mcp_server) -> None:
    result = run(mcp_server.call_tool("assess_impact", {"full_name": "SynappsTest.Services.TaskService.CreateTaskAsync"}))
    assert isinstance(text(result), str)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_usages_no_kind_returns_str(mcp_server) -> None:
    result = run(mcp_server.call_tool("find_usages", {"full_name": "SynappsTest.Services.ITaskService"}))
    assert isinstance(text(result), str)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_hierarchy_deprecated_returns_str(mcp_server) -> None:
    result = run(mcp_server.call_tool("get_hierarchy", {"full_name": "SynappsTest.Services.TaskService"}))
    assert isinstance(text(result), str)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_dependencies_deprecated_returns_str(mcp_server) -> None:
    result = run(mcp_server.call_tool("find_dependencies", {"full_name": "SynappsTest.Controllers.TaskController"}))
    assert isinstance(text(result), str)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_entry_points_deprecated_returns_str(mcp_server) -> None:
    result = run(mcp_server.call_tool("find_entry_points", {"full_name": "SynappsTest.Services.TaskService"}))
    assert isinstance(text(result), str)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_tests_for_deprecated_returns_str(mcp_server) -> None:
    result = run(mcp_server.call_tool("find_tests_for", {"full_name": "SynappsTest.Services.TaskService.CreateTaskAsync"}))
    assert isinstance(text(result), str)
