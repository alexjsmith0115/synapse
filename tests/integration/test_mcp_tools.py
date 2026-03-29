"""
MCP tool integration tests.

Requires Memgraph on localhost:7687 and .NET SDK.
Run with: pytest tests/integration/test_mcp_tools.py -v -m integration
"""
from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP

from synapps.service import SynappsService
from tests.integration.conftest import run, text, result_json, FIXTURE_PATH


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "index_project", "list_projects", "sync_project",
    "find_implementations", "find_callers",
    "find_callees", "get_hierarchy", "search_symbols", "summary",
    "execute_query", "find_usages", "find_dependencies",
    "get_context_for", "trace_call_chain", "find_entry_points",
    "analyze_change_impact",
    "get_schema",
    "find_http_endpoints", "trace_http_dependency",
}


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_all_tools_registered(mcp_server: FastMCP) -> None:
    tools = run(mcp_server.list_tools())
    names = {t.name for t in tools}
    assert EXPECTED_TOOLS == names


# ---------------------------------------------------------------------------
# Bug 1 regression: every controller action must have a CALLS edge
# ---------------------------------------------------------------------------

CONTROLLER_CALLS = [
    ("SynappsTest.Controllers.TaskController.Create", "CreateTaskAsync"),
    ("SynappsTest.Controllers.TaskController.Get", "GetTaskAsync"),
    ("SynappsTest.Controllers.TaskController.List", "ListTasksAsync"),
    ("SynappsTest.Controllers.TaskController.Update", "UpdateTaskAsync"),
    ("SynappsTest.Controllers.TaskController.Delete", "DeleteTaskAsync"),
    ("SynappsTest.Controllers.TaskController.Complete", "CompleteTaskAsync"),
]


@pytest.mark.integration
@pytest.mark.timeout(10)
@pytest.mark.parametrize("controller_method,expected_callee", CONTROLLER_CALLS)
def test_controller_calls_service_method(
    mcp_server: FastMCP, controller_method: str, expected_callee: str
) -> None:
    """Bug 1 regression: every TaskController action must have a CALLS edge
    to its corresponding ITaskService method."""
    result = run(mcp_server.call_tool("find_callees", {
        "method_full_name": controller_method
    }))
    callees = result_json(result)
    callee_names = [c.get("name", "") for c in (callees or [])]
    assert expected_callee in callee_names, (
        f"{controller_method} should call {expected_callee}, "
        f"got callees: {callee_names}"
    )


# ---------------------------------------------------------------------------
# Bug 2 regression: test references counted in find_type_impact
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_impact_counts_test_refs(mcp_server: FastMCP) -> None:
    """Bug 2 regression: find_usages with include_test_breakdown must count test project references."""
    result = run(mcp_server.call_tool("find_usages", {
        "full_name": "SynappsTest.Services.ITaskService",
        "include_test_breakdown": True,
    }))
    impact = result_json(result)
    assert impact["test_count"] > 0, (
        f"Expected test_count > 0 for ITaskService, got {impact['test_count']}. "
        f"References: {impact.get('references', [])}"
    )


# ---------------------------------------------------------------------------
# Project-level tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_projects(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("list_projects", {}))
    projects = result_json(result)
    paths = [p["path"] for p in projects]
    assert FIXTURE_PATH in paths


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_index_status(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("list_projects", {"path": FIXTURE_PATH}))
    status = result_json(result)
    assert status["file_count"] > 0
    assert status["symbol_count"] > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_schema(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_schema", {}))
    schema = result_json(result)
    assert "node_labels" in schema


# ---------------------------------------------------------------------------
# Symbol query tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("search_symbols", {
        "query": "Task", "kind": "Class"
    }))
    symbols = result_json(result)
    assert len(symbols) >= 1
    names = [s["full_name"] for s in symbols]
    assert any("Task" in n for n in names)


# ---------------------------------------------------------------------------
# Relationship query tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_implementations_task_service(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_implementations", {
        "interface_name": "SynappsTest.Services.ITaskService"
    }))
    impls = result_json(result)
    names = [i["full_name"] for i in impls]
    assert "SynappsTest.Services.TaskService" in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_implementations_project_service(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_implementations", {
        "interface_name": "SynappsTest.Services.IProjectService"
    }))
    impls = result_json(result)
    names = [i["full_name"] for i in impls]
    assert "SynappsTest.Services.ProjectService" in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callers(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_callers", {
        "method_full_name": "SynappsTest.Services.TaskService.CreateTaskAsync",
        "exclude_test_callers": False,
    }))
    callers = result_json(result)
    names = [c.get("full_name", "") for c in callers]
    assert any("Create" in n for n in names), (
        f"Expected TaskController.Create in callers, got: {names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callees(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_callees", {
        "method_full_name": "SynappsTest.Controllers.TaskController.Create"
    }))
    callees = result_json(result)
    names = [c.get("name", "") for c in callees]
    assert "CreateTaskAsync" in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_hierarchy_controller(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_hierarchy", {
        "class_name": "SynappsTest.Controllers.TaskController"
    }))
    hierarchy = result_json(result)
    parent_names = [p.get("full_name", "") for p in hierarchy["parents"]]
    assert any("BaseController" in n for n in parent_names)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_hierarchy_model(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_hierarchy", {
        "class_name": "SynappsTest.Models.TaskItem"
    }))
    hierarchy = result_json(result)
    parent_names = [p.get("full_name", "") for p in hierarchy["parents"]]
    assert any("BaseEntity" in n for n in parent_names)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_references(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_usages", {
        "full_name": "SynappsTest.Services.ITaskService",
        "kind": "parameter",
    }))
    refs = result_json(result)
    ref_names = [r.get("symbol", {}).get("full_name", "") for r in refs]
    assert any("TaskController" in n for n in ref_names), (
        f"Expected TaskController in type refs for ITaskService, got: {ref_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_dependencies(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_dependencies", {
        "full_name": "SynappsTest.Controllers.TaskController"
    }))
    deps = result_json(result)
    dep_names = [d["type"].get("full_name", "") for d in deps]
    assert any("ITaskService" in n for n in dep_names), (
        f"Expected ITaskService in dependencies for TaskController, got: {dep_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_context_for", {
        "full_name": "SynappsTest.Controllers.TaskController"
    }))
    ctx = text(result)
    assert len(ctx) > 0
    assert "TaskController" in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_structure_scope(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_context_for", {
        "full_name": "SynappsTest.Services.TaskService",
        "scope": "structure",
    }))
    ctx = text(result)
    assert "## Members" in ctx
    assert "TaskService" in ctx
    # Structure scope should NOT contain full source body or callees
    assert "## Called Methods" not in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_method_scope(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_context_for", {
        "full_name": "SynappsTest.Services.TaskService.CreateTaskAsync",
        "scope": "method",
    }))
    ctx = text(result)
    assert "## Target:" in ctx
    assert "CreateTaskAsync" in ctx
    # Method scope should NOT contain full containing type member list
    assert "## Containing Type:" not in ctx
    assert "## Members:" not in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_edit_scope_method(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_context_for", {
        "full_name": "SynappsTest.Services.TaskService.CreateTaskAsync",
        "scope": "edit",
    }))
    ctx = text(result)
    assert "## Target:" in ctx
    assert "CreateTaskAsync" in ctx
    # Edit scope should NOT contain full containing type member list or callees
    assert "## Containing Type:" not in ctx
    assert "## Called Methods" not in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_edit_scope_class(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_context_for", {
        "full_name": "SynappsTest.Services.TaskService",
        "scope": "edit",
    }))
    ctx = text(result)
    assert "## Target:" in ctx
    assert "TaskService" in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_edit_scope_rejects_field(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_context_for", {
        "full_name": "SynappsTest.Models.BaseEntity._createdBy",
        "scope": "edit",
    }))
    ctx = text(result)
    assert "scope='edit' requires" in ctx


# ---------------------------------------------------------------------------
# Call chain / entry point / impact tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_trace_call_chain(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("trace_call_chain", {
        "start": "SynappsTest.Controllers.TaskController.Create",
        "end": "SynappsTest.Services.ProjectService.ValidateProjectAsync",
    }))
    trace = result_json(result)
    assert len(trace["paths"]) > 0, (
        "Expected at least one path from TaskController.Create to "
        "ProjectService.ValidateProjectAsync"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_entry_points(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_entry_points", {
        "method": "SynappsTest.Services.ProjectService.ValidateProjectAsync",
        "exclude_test_callers": False,
    }))
    ep = result_json(result)
    entries = [e["entry"] for e in ep["entry_points"]]
    assert any("TaskController" in e for e in entries), (
        f"Expected TaskController as entry point, got: {entries}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_analyze_change_impact(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("analyze_change_impact", {
        "method": "SynappsTest.Services.TaskService.CreateTaskAsync",
    }))
    output = text(result)
    # analyze_change_impact returns compact markdown. Verify the tool
    # returns key sections with callees and test coverage.
    assert "Change Impact" in output
    assert "CreateTaskAsync" in output
    assert "Test Coverage" in output or "Callees" in output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_call_depth(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_callees", {
        "method_full_name": "SynappsTest.Controllers.TaskController.Create",
        "depth": 3,
    }))
    depth_result = result_json(result)
    assert len(depth_result["callees"]) > 0


# ---------------------------------------------------------------------------
# Summary tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_set_and_get_summary(mcp_server: FastMCP) -> None:
    run(mcp_server.call_tool("summary", {
        "action": "set",
        "full_name": "SynappsTest.Services.TaskService",
        "content": "Manages task CRUD operations.",
    }))
    result = run(mcp_server.call_tool("summary", {
        "action": "get",
        "full_name": "SynappsTest.Services.TaskService",
    }))
    assert text(result) == "Manages task CRUD operations."


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_summarized(mcp_server: FastMCP) -> None:
    run(mcp_server.call_tool("summary", {
        "action": "set",
        "full_name": "SynappsTest.Services.TaskService",
        "content": "Manages task CRUD operations.",
    }))
    result = run(mcp_server.call_tool("summary", {"action": "list"}))
    items = result_json(result)
    names = [i.get("full_name") for i in items]
    assert "SynappsTest.Services.TaskService" in names


# ---------------------------------------------------------------------------
# Execute query
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_valid_query(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("execute_query", {
        "cypher": "MATCH (n:Class) RETURN n.name LIMIT 5"
    }))
    rows = result_json(result)
    assert isinstance(rows, list)
    assert len(rows) > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_mutating_query_blocked(mcp_server: FastMCP) -> None:
    with pytest.raises(Exception):
        run(mcp_server.call_tool("execute_query", {
            "cypher": "CREATE (n:Fake) RETURN n"
        }))


# ---------------------------------------------------------------------------
# Bug 1 regression: find_callers must exclude test-project callers when asked
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callers_excludes_test_callers(service: SynappsService) -> None:
    """Bug 1 regression: exclude_test_callers=True must filter callers
    whose file_path lives inside a SynappsTest.Tests directory."""
    all_callers = service.find_callers("SynappsTest.Services.TaskService.CreateTaskAsync", exclude_test_callers=False)
    filtered_callers = service.find_callers(
        "SynappsTest.Services.TaskService.CreateTaskAsync",
        exclude_test_callers=True,
    )

    # Core: no test-project callers survive the filter
    test_callers_in_filtered = [
        c for c in filtered_callers
        if "SynappsTest.Tests" in c.get("file_path", "")
    ]
    assert test_callers_in_filtered == [], (
        f"Expected no test-project callers with exclude_test_callers=True, "
        f"got: {test_callers_in_filtered}"
    )

    # Filter must not add callers
    assert len(filtered_callers) <= len(all_callers)

    # Non-vacuous: test caller must appear without the flag
    test_callers_in_all = [
        c for c in all_callers
        if "SynappsTest.Tests" in c.get("file_path", "")
    ]
    assert len(test_callers_in_all) > 0, (
        "Expected at least one caller from SynappsTest.Tests in all_callers. "
        "The direct call in TaskServiceTests.TestCreateTask may not have been indexed."
    )
