"""
MCP tool integration tests.

Requires FalkorDB on localhost:6379 and .NET SDK.
Run with: pytest tests/integration/test_mcp_tools.py -v -m integration
"""
from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP

from synapse.service import SynapseService
from tests.integration.conftest import run, text, result_json, FIXTURE_PATH


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "index_project", "list_projects", "delete_project", "get_index_status",
    "get_symbol", "get_symbol_source", "find_implementations", "find_callers",
    "find_callees", "get_hierarchy", "search_symbols", "set_summary",
    "get_summary", "list_summarized", "execute_query", "watch_project",
    "unwatch_project", "find_type_references", "find_dependencies",
    "get_context_for", "trace_call_chain", "find_entry_points",
    "get_call_depth", "analyze_change_impact", "find_interface_contract",
    "find_type_impact", "audit_architecture", "summarize_from_graph",
    "get_schema",
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
    ("SynapseTest.Controllers.TaskController.Create", "CreateTaskAsync"),
    ("SynapseTest.Controllers.TaskController.Get", "GetTaskAsync"),
    ("SynapseTest.Controllers.TaskController.List", "ListTasksAsync"),
    ("SynapseTest.Controllers.TaskController.Update", "UpdateTaskAsync"),
    ("SynapseTest.Controllers.TaskController.Delete", "DeleteTaskAsync"),
    ("SynapseTest.Controllers.TaskController.Complete", "CompleteTaskAsync"),
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
    """Bug 2 regression: find_type_impact must count test project references."""
    result = run(mcp_server.call_tool("find_type_impact", {
        "type_name": "SynapseTest.Services.ITaskService"
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
    result = run(mcp_server.call_tool("get_index_status", {"path": FIXTURE_PATH}))
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
def test_get_symbol(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_symbol", {
        "full_name": "SynapseTest.Services.TaskService"
    }))
    symbol = result_json(result)
    assert symbol is not None
    assert symbol["full_name"] == "SynapseTest.Services.TaskService"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_not_found(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_symbol", {
        "full_name": "DoesNotExist.Nope"
    }))
    assert result_json(result) is None


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_source(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_symbol_source", {
        "full_name": "SynapseTest.Controllers.TaskController"
    }))
    source = text(result)
    assert "TaskController" in source
    assert "_taskService" in source


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
        "interface_name": "SynapseTest.Services.ITaskService"
    }))
    impls = result_json(result)
    names = [i["full_name"] for i in impls]
    assert "SynapseTest.Services.TaskService" in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_implementations_project_service(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_implementations", {
        "interface_name": "SynapseTest.Services.IProjectService"
    }))
    impls = result_json(result)
    names = [i["full_name"] for i in impls]
    assert "SynapseTest.Services.ProjectService" in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callers(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_callers", {
        "method_full_name": "SynapseTest.Services.TaskService.CreateTaskAsync"
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
        "method_full_name": "SynapseTest.Controllers.TaskController.Create"
    }))
    callees = result_json(result)
    names = [c.get("name", "") for c in callees]
    assert "CreateTaskAsync" in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_hierarchy_controller(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_hierarchy", {
        "class_name": "SynapseTest.Controllers.TaskController"
    }))
    hierarchy = result_json(result)
    parent_names = [p.get("full_name", "") for p in hierarchy["parents"]]
    assert any("BaseController" in n for n in parent_names)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_hierarchy_model(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_hierarchy", {
        "class_name": "SynapseTest.Models.TaskItem"
    }))
    hierarchy = result_json(result)
    parent_names = [p.get("full_name", "") for p in hierarchy["parents"]]
    assert any("BaseEntity" in n for n in parent_names)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_references(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_type_references", {
        "full_name": "SynapseTest.Services.ITaskService"
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
        "full_name": "SynapseTest.Controllers.TaskController"
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
        "full_name": "SynapseTest.Controllers.TaskController"
    }))
    ctx = text(result)
    assert len(ctx) > 0
    assert "TaskController" in ctx


# ---------------------------------------------------------------------------
# Call chain / entry point / impact tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_trace_call_chain(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("trace_call_chain", {
        "start": "SynapseTest.Controllers.TaskController.Create",
        "end": "SynapseTest.Services.ProjectService.ValidateProjectAsync",
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
        "method": "SynapseTest.Services.ProjectService.ValidateProjectAsync",
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
        "method": "SynapseTest.Services.TaskService.CreateTaskAsync",
    }))
    impact = result_json(result)
    caller_names = [c["full_name"] for c in impact["direct_callers"]]
    assert any("TaskController" in n for n in caller_names), (
        f"Expected TaskController in direct callers, got: {caller_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_call_depth(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_call_depth", {
        "method": "SynapseTest.Controllers.TaskController.Create",
        "depth": 3,
    }))
    depth_result = result_json(result)
    assert len(depth_result["callees"]) > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_interface_contract(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_interface_contract", {
        "method": "SynapseTest.Services.TaskService.CreateTaskAsync",
    }))
    contract = result_json(result)
    assert "ITaskService" in (contract.get("interface") or ""), (
        f"Expected ITaskService as interface, got: {contract}"
    )


# ---------------------------------------------------------------------------
# Audit / summarize tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_audit_architecture(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("audit_architecture", {
        "rule": "untested_services",
    }))
    audit = result_json(result)
    assert audit["rule"] == "untested_services"
    assert "count" in audit


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_summarize_from_graph(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("summarize_from_graph", {
        "class_name": "SynapseTest.Services.TaskService",
    }))
    summary = result_json(result)
    assert summary is not None
    assert "summary" in summary


# ---------------------------------------------------------------------------
# Summary tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_set_and_get_summary(mcp_server: FastMCP) -> None:
    run(mcp_server.call_tool("set_summary", {
        "full_name": "SynapseTest.Services.TaskService",
        "content": "Manages task CRUD operations.",
    }))
    result = run(mcp_server.call_tool("get_summary", {
        "full_name": "SynapseTest.Services.TaskService"
    }))
    assert text(result) == "Manages task CRUD operations."


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_summarized(mcp_server: FastMCP) -> None:
    run(mcp_server.call_tool("set_summary", {
        "full_name": "SynapseTest.Services.TaskService",
        "content": "Manages task CRUD operations.",
    }))
    result = run(mcp_server.call_tool("list_summarized", {}))
    items = result_json(result)
    names = [i.get("full_name") for i in items]
    assert "SynapseTest.Services.TaskService" in names


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
# Watch tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_watch_and_unwatch(mcp_server: FastMCP) -> None:
    watch_result = run(mcp_server.call_tool("watch_project", {"path": FIXTURE_PATH}))
    assert FIXTURE_PATH in text(watch_result)
    unwatch_result = run(mcp_server.call_tool("unwatch_project", {"path": FIXTURE_PATH}))
    assert FIXTURE_PATH in text(unwatch_result)


# ---------------------------------------------------------------------------
# Bug 1 regression: find_callers must exclude test-project callers when asked
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callers_excludes_test_callers(service: SynapseService) -> None:
    """Bug 1 regression: exclude_test_callers=True must filter callers
    whose file_path lives inside a SynapseTest.Tests directory."""
    all_callers = service.find_callers("SynapseTest.Services.TaskService.CreateTaskAsync")
    filtered_callers = service.find_callers(
        "SynapseTest.Services.TaskService.CreateTaskAsync",
        exclude_test_callers=True,
    )

    # Core: no test-project callers survive the filter
    test_callers_in_filtered = [
        c for c in filtered_callers
        if "SynapseTest.Tests" in c.get("file_path", "")
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
        if "SynapseTest.Tests" in c.get("file_path", "")
    ]
    assert len(test_callers_in_all) > 0, (
        "Expected at least one caller from SynapseTest.Tests in all_callers. "
        "The direct call in TaskServiceTests.TestCreateTask may not have been indexed."
    )
