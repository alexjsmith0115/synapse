"""
MCP tool integration tests.

Requires Memgraph on localhost:7687 and .NET SDK.
Run with: pytest tests/integration/test_mcp_tools.py -v -m integration
"""
from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP

from synapps.service import SynappsService
from synapps.graph.connection import GraphConnection
from tests.integration.conftest import run, text, result_json, FIXTURE_PATH


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "index_project", "list_projects", "sync_project",
    "find_implementations",
    "find_callees", "get_hierarchy", "search_symbols", "summary",
    "execute_query", "find_usages", "find_dependencies",
    "get_context_for", "find_entry_points",
    "get_schema",
    "find_http_endpoints",
    "get_architecture",
    "find_dead_code", "find_tests_for", "find_untested",
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
        "full_name": controller_method
    }))
    callees = result_json(result)
    callee_names = [c.get("name", "") for c in (callees or [])]
    assert expected_callee in callee_names, (
        f"{controller_method} should call {expected_callee}, "
        f"got callees: {callee_names}"
    )


# ---------------------------------------------------------------------------
# Project-level tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_projects(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("list_projects", {}))
    data = result_json(result)
    assert "synapps_mcp_version" in data
    projects = data["projects"]
    paths = [p["path"] for p in projects]
    assert FIXTURE_PATH in paths


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_index_status(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("list_projects", {"path": FIXTURE_PATH}))
    status = result_json(result)
    assert "synapps_mcp_version" in status
    assert status["file_count"] > 0
    assert status["symbol_count"] > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_schema(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_schema", {}))
    schema = result_json(result)
    assert "node_labels" in schema


@pytest.mark.integration
@pytest.mark.timeout(60)
def test_index_project(mcp_server: FastMCP) -> None:
    """index_project re-indexes the C# fixture without error."""
    result = run(mcp_server.call_tool("index_project", {
        "path": FIXTURE_PATH,
        "language": "csharp",
    }))
    msg = text(result)
    assert "Indexed" in msg


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


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols_language_filter(mcp_server: FastMCP) -> None:
    """search_symbols with language filter returns only C# symbols."""
    result = run(mcp_server.call_tool("search_symbols", {
        "query": "Task",
        "language": "csharp",
    }))
    symbols = result_json(result)
    for sym in symbols:
        assert sym.get("language") == "csharp"


# ---------------------------------------------------------------------------
# Relationship query tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_implementations_task_service(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_implementations", {
        "full_name": "SynappsTest.Services.ITaskService"
    }))
    impls = result_json(result)
    names = [i["full_name"] for i in impls]
    assert "SynappsTest.Services.TaskService" in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_implementations_project_service(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_implementations", {
        "full_name": "SynappsTest.Services.IProjectService"
    }))
    impls = result_json(result)
    names = [i["full_name"] for i in impls]
    assert "SynappsTest.Services.ProjectService" in names


# ---------------------------------------------------------------------------
# Generic type IMPLEMENTS regression: classes with <T> in full_name must
# still get IMPLEMENTS edges (bug: file_type_names key included generics
# but tree-sitter extractor returns bare identifier).
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_generic_class_implements_generic_interface(mcp_server: FastMCP) -> None:
    """TaskRepository IMPLEMENTS IRepository<T> — generic full_names must not break edge creation."""
    result = run(mcp_server.call_tool("find_implementations", {
        "full_name": "SynappsTest.Services.IRepository<T>"
    }))
    impls = result_json(result)
    names = [i["full_name"] for i in impls]
    assert "SynappsTest.Services.TaskRepository" in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_generic_interface_dispatches_to_impl(service: SynappsService) -> None:
    """Methods on generic interface must have DISPATCHES_TO edges to implementing class methods."""
    rows = service._conn.query(
        "MATCH (iface:Method)-[:DISPATCHES_TO]->(impl:Method) "
        "WHERE iface.full_name STARTS WITH 'SynappsTest.Services.IRepository<T>.' "
        "RETURN iface.name, impl.full_name "
        "ORDER BY iface.name"
    )
    dispatched_names = {r[0] for r in rows}
    assert "GetByIdAsync" in dispatched_names, (
        f"Expected DISPATCHES_TO for GetByIdAsync, got: {dispatched_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callees(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_callees", {
        "full_name": "SynappsTest.Controllers.TaskController.Create"
    }))
    callees = result_json(result)
    names = [c.get("name", "") for c in callees]
    assert "CreateTaskAsync" in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_hierarchy_controller(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_hierarchy", {
        "full_name": "SynappsTest.Controllers.TaskController"
    }))
    hierarchy = result_json(result)
    parent_names = [p.get("full_name", "") for p in hierarchy["parents"]]
    assert any("BaseController" in n for n in parent_names)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_hierarchy_model(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_hierarchy", {
        "full_name": "SynappsTest.Models.TaskItem"
    }))
    hierarchy = result_json(result)
    parent_names = [p.get("full_name", "") for p in hierarchy["parents"]]
    assert any("BaseEntity" in n for n in parent_names)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_usages(mcp_server: FastMCP) -> None:
    """find_usages returns compact text summary for a C# interface."""
    result = run(mcp_server.call_tool("find_usages", {
        "full_name": "SynappsTest.Services.ITaskService"
    }))
    output = text(result)
    assert "Usages of" in output
    assert "ITaskService" in output


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
def test_find_entry_points(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_entry_points", {
        "full_name": "SynappsTest.Services.ProjectService.ValidateProjectAsync",
        "exclude_test_callers": False,
    }))
    ep = result_json(result)
    entries = [e["entry"] for e in ep["entry_points"]]
    assert any("TaskController" in e for e in entries), (
        f"Expected TaskController as entry point, got: {entries}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_impact(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("get_context_for", {
        "full_name": "SynappsTest.Services.TaskService.CreateTaskAsync",
        "scope": "impact",
    }))
    output = text(result)
    assert "Change Impact" in output
    assert "CreateTaskAsync" in output
    assert "Test Coverage" in output or "Callees" in output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_call_depth(mcp_server: FastMCP) -> None:
    result = run(mcp_server.call_tool("find_callees", {
        "full_name": "SynappsTest.Controllers.TaskController.Create",
        "depth": 3,
    }))
    depth_result = result_json(result)
    assert len(depth_result["callees"]) > 0


# ---------------------------------------------------------------------------
# Summary tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_summary_no_summary(mcp_server: FastMCP) -> None:
    """summary action=get returns None when no summary set for C# symbol."""
    result = run(mcp_server.call_tool("summary", {
        "action": "get",
        "full_name": "SynappsTest.Services.ProjectService",
    }))
    summary = result_json(result)
    assert summary is None or isinstance(summary, str)


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
# Cross-file CALLS edge verification
# ---------------------------------------------------------------------------

# Each entry: (caller_full_name, callee_full_name) — both MUST be in different files.
CROSS_FILE_CALLS = [
    (
        "SynappsTest.Controllers.TaskController.Create",
        "SynappsTest.Services.ITaskService.CreateTaskAsync",
    ),
    (
        "SynappsTest.Controllers.TaskController.Get",
        "SynappsTest.Services.ITaskService.GetTaskAsync",
    ),
    (
        "SynappsTest.Controllers.TaskController.Delete",
        "SynappsTest.Services.ITaskService.DeleteTaskAsync",
    ),
    (
        "SynappsTest.Services.TaskService.CreateTaskAsync",
        "SynappsTest.Services.IProjectService.ValidateProjectAsync",
    ),
]


@pytest.mark.integration
@pytest.mark.timeout(10)
@pytest.mark.parametrize("caller,callee", CROSS_FILE_CALLS)
def test_cross_file_calls_edge_exists(
    service: SynappsService, caller: str, callee: str
) -> None:
    """Verify that CALLS edges are created for method invocations across files."""
    rows = service._conn.query(
        "MATCH (src:Method {full_name: $caller})-[r:CALLS]->"
        "(dst:Method {full_name: $callee}) "
        "RETURN src.full_name, dst.full_name",
        {"caller": caller, "callee": callee},
    )
    assert rows, (
        f"Expected CALLS edge from {caller} to {callee}, but none found. "
        f"This is a cross-file call that should be resolved by the LSP."
    )


# ---------------------------------------------------------------------------
# Generic method call CALLS edge verification
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_generic_method_call_creates_calls_edge(service: SynappsService) -> None:
    """Generic invocations like _service.Method<T>() must produce CALLS edges."""
    rows = service._conn.query(
        "MATCH (src:Method {full_name: $caller})-[r:CALLS]->(dst:Method) "
        "WHERE dst.full_name CONTAINS 'ConvertTask' "
        "RETURN dst.full_name",
        {"caller": "SynappsTest.Controllers.TaskController.Convert"},
    )
    assert rows, (
        "Expected CALLS edge from TaskController.Convert to a ConvertTask method "
        "(generic call _taskService.ConvertTask<object>(task)), but none found."
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_generic_method_call_via_find_callees(mcp_server: FastMCP) -> None:
    """find_callees must return the target of a generic method invocation."""
    result = run(mcp_server.call_tool("find_callees", {
        "full_name": "SynappsTest.Controllers.TaskController.Convert"
    }))
    callees = result_json(result)
    callee_names = [c.get("name", "") for c in (callees or [])]
    assert any("ConvertTask" in n for n in callee_names), (
        f"TaskController.Convert calls _taskService.ConvertTask<object>() "
        f"but find_callees returned: {callee_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_null_conditional_call_via_find_callees(mcp_server: FastMCP) -> None:
    """D-01/D-02 regression: obj?.Method() must produce a CALLS edge."""
    result = run(mcp_server.call_tool("find_callees", {
        "full_name": "SynappsTest.Services.NullConditionalHost.RunIfPresent"
    }))
    callees = result_json(result)
    callee_names = [c.get("name", "") for c in (callees or [])]
    assert "GetTaskAsync" in callee_names, (
        f"NullConditionalHost.RunIfPresent calls _service?.GetTaskAsync() "
        f"but find_callees returned: {callee_names}"
    )


# ---------------------------------------------------------------------------
# DISPATCHES_TO edge verification
# ---------------------------------------------------------------------------

# Each entry: (interface_method, concrete_method) — interface dispatches to impl.
DISPATCHES_TO_EDGES = [
    (
        "SynappsTest.Services.ITaskService.CreateTaskAsync",
        "SynappsTest.Services.TaskService.CreateTaskAsync",
    ),
    (
        "SynappsTest.Services.ITaskService.GetTaskAsync",
        "SynappsTest.Services.TaskService.GetTaskAsync",
    ),
    (
        "SynappsTest.Services.ITaskService.DeleteTaskAsync",
        "SynappsTest.Services.TaskService.DeleteTaskAsync",
    ),
    (
        "SynappsTest.Services.IProjectService.ValidateProjectAsync",
        "SynappsTest.Services.ProjectService.ValidateProjectAsync",
    ),
]


@pytest.mark.integration
@pytest.mark.timeout(10)
@pytest.mark.parametrize("iface_method,impl_method", DISPATCHES_TO_EDGES)
def test_dispatches_to_edge_exists(
    service: SynappsService, iface_method: str, impl_method: str
) -> None:
    """Verify that DISPATCHES_TO edges connect interface methods to implementations."""
    rows = service._conn.query(
        "MATCH (iface:Method {full_name: $iface})-[r:DISPATCHES_TO]->"
        "(impl:Method {full_name: $impl}) "
        "RETURN iface.full_name, impl.full_name",
        {"iface": iface_method, "impl": impl_method},
    )
    assert rows, (
        f"Expected DISPATCHES_TO edge from {iface_method} to {impl_method}, "
        f"but none found."
    )


# ---------------------------------------------------------------------------
# Reindex (sync) path: cross-file edges must survive single-file reindex
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(30)
def test_reindex_preserves_cross_file_calls(service: SynappsService) -> None:
    """After reindexing TaskController.cs, cross-file CALLS edges must still exist.

    reindex_file deletes outgoing edges for the file and re-resolves them.
    This test verifies that cross-file call resolution works with the
    single-file symbol_map used by reindex_file.
    """
    import os
    from synapps.indexer.indexer import Indexer
    from synapps.plugin.csharp import CSharpPlugin

    controller_path = os.path.join(FIXTURE_PATH, "Controllers", "TaskController.cs")
    plugin = CSharpPlugin()
    lsp = plugin.create_lsp_adapter(FIXTURE_PATH)
    try:
        indexer = Indexer(service._conn, lsp, plugin=plugin)
        indexer.reindex_file(controller_path, FIXTURE_PATH)
    finally:
        lsp.shutdown()

    # Verify cross-file CALLS edges still exist after reindex
    rows = service._conn.query(
        "MATCH (src:Method {full_name: $caller})-[r:CALLS]->"
        "(dst:Method {full_name: $callee}) "
        "RETURN src.full_name, dst.full_name",
        {
            "caller": "SynappsTest.Controllers.TaskController.Create",
            "callee": "SynappsTest.Services.ITaskService.CreateTaskAsync",
        },
    )
    assert rows, (
        "Cross-file CALLS edge from TaskController.Create to "
        "ITaskService.CreateTaskAsync was lost after reindex_file"
    )


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_reindex_preserves_dispatches_to(service: SynappsService) -> None:
    """After reindexing TaskService.cs, DISPATCHES_TO edges must still exist.

    reindex_file deletes outgoing edges including DISPATCHES_TO.
    MethodImplementsIndexer must run to recreate them.
    """
    import os
    from synapps.indexer.indexer import Indexer
    from synapps.plugin.csharp import CSharpPlugin

    service_path = os.path.join(FIXTURE_PATH, "Services", "TaskService.cs")
    plugin = CSharpPlugin()
    lsp = plugin.create_lsp_adapter(FIXTURE_PATH)
    try:
        indexer = Indexer(service._conn, lsp, plugin=plugin)
        indexer.reindex_file(service_path, FIXTURE_PATH)
    finally:
        lsp.shutdown()

    # Check IMPLEMENTS edge (prerequisite for DISPATCHES_TO)
    impl_rows = service._conn.query(
        "MATCH (c:Class {full_name: $cls})-[r:IMPLEMENTS]->(i) "
        "RETURN type(r), i.full_name",
        {"cls": "SynappsTest.Services.TaskService"},
    )
    assert impl_rows, (
        "IMPLEMENTS edge from TaskService to ITaskService was lost after reindex_file. "
        "DISPATCHES_TO depends on this edge."
    )

    # Verify DISPATCHES_TO edges still exist after reindex
    rows = service._conn.query(
        "MATCH (iface:Method {full_name: $iface})-[r:DISPATCHES_TO]->"
        "(impl:Method {full_name: $impl}) "
        "RETURN iface.full_name, impl.full_name",
        {
            "iface": "SynappsTest.Services.ITaskService.CreateTaskAsync",
            "impl": "SynappsTest.Services.TaskService.CreateTaskAsync",
        },
    )
    assert rows, (
        "DISPATCHES_TO edge from ITaskService.CreateTaskAsync to "
        "TaskService.CreateTaskAsync was lost after reindex_file"
    )


# ---------------------------------------------------------------------------
# Attribute property verification (TaskController: [ApiController], [Route])
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_attributes_populated_on_csharp_nodes(mcp_server: FastMCP) -> None:
    """n.attributes JSON property is populated for attributed C# symbols after indexing."""
    result = run(mcp_server.call_tool("execute_query", {
        "cypher": (
            "MATCH (n {full_name: 'SynappsTest.Controllers.TaskController'}) "
            "RETURN n.attributes"
        )
    }))
    rows = result_json(result)
    assert rows and len(rows) > 0, "TaskController node not found in graph"
    attributes_value = rows[0]["row"][0]
    assert attributes_value is not None, (
        "n.attributes is null on TaskController — attribute extraction pipeline not writing to graph"
    )
    assert "ApiController" in attributes_value, (
        f"Expected 'ApiController' in TaskController.attributes, got: {attributes_value}"
    )


# ---------------------------------------------------------------------------
# VALID-02: delegate argument (method group) produces CALLS edge
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_delegate_argument_produces_calls_edge(service: SynappsService) -> None:
    """VALID-02: C# method group passed as delegate argument must produce CALLS edge via ReferencesResolver."""
    rows = service._conn.query(
        "MATCH (caller:Method)-[:CALLS]->(callee:Method) "
        "WHERE caller.full_name CONTAINS 'CallWithMethodGroup' "
        "AND callee.name = 'GetTaskAsync' "
        "RETURN caller.full_name, callee.full_name LIMIT 1"
    )
    assert rows, (
        "Expected CALLS edge from DelegateHost.CallWithMethodGroup to ITaskService.GetTaskAsync "
        "(via method group _service.GetTaskAsync passed as Func<> delegate argument), "
        "but none found in graph. ReferencesResolver must index method group references."
    )

