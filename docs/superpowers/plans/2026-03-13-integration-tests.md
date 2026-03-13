# Integration Tests Redesign — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the minimal SynapseTest fixture and integration tests with a richer task management fixture that covers all 29 MCP tools, 26 CLI commands, and regression cases from the bug report.

**Architecture:** Single C# fixture project (+ test sub-project) indexed once via session-scoped pytest fixture. Two test files share the indexed graph via conftest.py. MCP tools tested via FastMCP `call_tool`, CLI commands via Typer `CliRunner`. Hybrid assertion strategy: exact for regressions and core correctness, structural for coverage.

**Tech Stack:** pytest, FastMCP 1.26, Typer CliRunner, FalkorDB, .NET SDK (for LSP indexing)

**Spec:** `docs/specs/2026-03-13-integration-tests-design.md`

---

## Chunk 1: Fixture C# Project

### Task 1: Replace fixture project files

Replace the existing Animal-themed fixture with the task management domain.

**Files:**
- Delete: `tests/fixtures/SynapseTest/IAnimal.cs`
- Delete: `tests/fixtures/SynapseTest/Animal.cs`
- Delete: `tests/fixtures/SynapseTest/Dog.cs`
- Delete: `tests/fixtures/SynapseTest/Cat.cs`
- Delete: `tests/fixtures/SynapseTest/AnimalService.cs`
- Delete: `tests/fixtures/SynapseTest/Greeter.cs`
- Delete: `tests/fixtures/SynapseTest/Formatter.cs`
- Create: `tests/fixtures/SynapseTest/Models/BaseEntity.cs`
- Create: `tests/fixtures/SynapseTest/Models/TaskItem.cs`
- Create: `tests/fixtures/SynapseTest/Models/Project.cs`
- Create: `tests/fixtures/SynapseTest/Services/ITaskService.cs`
- Create: `tests/fixtures/SynapseTest/Services/TaskService.cs`
- Create: `tests/fixtures/SynapseTest/Services/IProjectService.cs`
- Create: `tests/fixtures/SynapseTest/Services/ProjectService.cs`
- Create: `tests/fixtures/SynapseTest/Controllers/BaseController.cs`
- Create: `tests/fixtures/SynapseTest/Controllers/TaskController.cs`
- Create: `tests/fixtures/SynapseTest/SynapseTest.Tests/SynapseTest.Tests.csproj`
- Create: `tests/fixtures/SynapseTest/SynapseTest.Tests/TaskServiceTests.cs`
- Modify: `tests/fixtures/SynapseTest/SynapseTest.csproj`

- [ ] **Step 1: Delete old .cs files**

```bash
cd tests/fixtures/SynapseTest
rm -f IAnimal.cs Animal.cs Dog.cs Cat.cs AnimalService.cs Greeter.cs Formatter.cs
```

- [ ] **Step 2: Create directory structure**

```bash
mkdir -p Models Services Controllers SynapseTest.Tests
```

- [ ] **Step 3: Update SynapseTest.csproj**

Keep net8.0, add nullable + implicit usings to match modern C# patterns:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
```

- [ ] **Step 4: Write Models/BaseEntity.cs**

```csharp
namespace SynapseTest.Models;

public abstract class BaseEntity
{
    public Guid Id { get; set; }
    public DateTime CreatedAt { get; set; }
    protected string _createdBy = "";
}
```

- [ ] **Step 5: Write Models/Project.cs**

```csharp
namespace SynapseTest.Models;

public class Project : BaseEntity
{
    public string Name { get; set; } = "";
    public ICollection<TaskItem> Tasks { get; set; } = new List<TaskItem>();
}
```

- [ ] **Step 6: Write Models/TaskItem.cs**

```csharp
namespace SynapseTest.Models;

public class TaskItem : BaseEntity
{
    public string Title { get; set; } = "";
    public bool IsComplete { get; set; }
    public Guid ProjectId { get; set; }
    public Project? Project { get; set; }
}
```

- [ ] **Step 7: Write Services/ITaskService.cs**

Six async methods — the exact count matters for bug 1 regression:

```csharp
namespace SynapseTest.Services;

using SynapseTest.Models;

public interface ITaskService
{
    Task<TaskItem> CreateTaskAsync(string title, Guid projectId);
    Task<TaskItem?> GetTaskAsync(Guid id);
    Task<List<TaskItem>> ListTasksAsync(Guid projectId);
    Task<TaskItem> UpdateTaskAsync(Guid id, string title);
    Task DeleteTaskAsync(Guid id);
    Task<TaskItem> CompleteTaskAsync(Guid id);
}
```

- [ ] **Step 8: Write Services/IProjectService.cs**

```csharp
namespace SynapseTest.Services;

using SynapseTest.Models;

public interface IProjectService
{
    Task<Project> GetProjectAsync(Guid id);
    Task ValidateProjectAsync(Guid id);
}
```

- [ ] **Step 9: Write Services/ProjectService.cs**

`ValidateProjectAsync` calls `GetProjectAsync` (intra-class call):

```csharp
namespace SynapseTest.Services;

using SynapseTest.Models;

public class ProjectService : IProjectService
{
    public Task<Project> GetProjectAsync(Guid id)
    {
        return Task.FromResult(new Project { Id = id, Name = "Default" });
    }

    public Task ValidateProjectAsync(Guid id)
    {
        GetProjectAsync(id);
        return Task.CompletedTask;
    }
}
```

- [ ] **Step 10: Write Services/TaskService.cs**

Implements `ITaskService`, injects `IProjectService` via constructor. Key methods call `_projectService` to create cross-service CALLS edges:

```csharp
namespace SynapseTest.Services;

using SynapseTest.Models;

public class TaskService : ITaskService
{
    private readonly IProjectService _projectService;

    public TaskService(IProjectService projectService)
    {
        _projectService = projectService;
    }

    public Task<TaskItem> CreateTaskAsync(string title, Guid projectId)
    {
        _projectService.ValidateProjectAsync(projectId);
        return Task.FromResult(new TaskItem { Title = title, ProjectId = projectId });
    }

    public Task<TaskItem?> GetTaskAsync(Guid id)
    {
        return Task.FromResult<TaskItem?>(new TaskItem { Id = id });
    }

    public Task<List<TaskItem>> ListTasksAsync(Guid projectId)
    {
        return Task.FromResult(new List<TaskItem>());
    }

    public Task<TaskItem> UpdateTaskAsync(Guid id, string title)
    {
        return Task.FromResult(new TaskItem { Id = id, Title = title });
    }

    public Task DeleteTaskAsync(Guid id)
    {
        return Task.CompletedTask;
    }

    public Task<TaskItem> CompleteTaskAsync(Guid id)
    {
        return Task.FromResult(new TaskItem { Id = id, IsComplete = true });
    }
}
```

- [ ] **Step 11: Write Controllers/BaseController.cs**

```csharp
namespace SynapseTest.Controllers;

public abstract class BaseController
{
    protected Guid GetUserId()
    {
        return Guid.NewGuid();
    }

    protected Guid ConvertToGuid(string value)
    {
        return Guid.Parse(value);
    }
}
```

- [ ] **Step 12: Write Controllers/TaskController.cs**

Six action methods, each calling the corresponding `_taskService` method via interface dispatch. This is the **bug 1 regression** surface:

```csharp
namespace SynapseTest.Controllers;

using SynapseTest.Models;
using SynapseTest.Services;

public class TaskController : BaseController
{
    private readonly ITaskService _taskService;

    public TaskController(ITaskService taskService)
    {
        _taskService = taskService;
    }

    public Task<TaskItem> Create(string title, Guid projectId)
    {
        return _taskService.CreateTaskAsync(title, projectId);
    }

    public Task<TaskItem?> Get(Guid id)
    {
        return _taskService.GetTaskAsync(id);
    }

    public Task<List<TaskItem>> List(Guid projectId)
    {
        return _taskService.ListTasksAsync(projectId);
    }

    public Task<TaskItem> Update(Guid id, string title)
    {
        return _taskService.UpdateTaskAsync(id, title);
    }

    public Task Delete(Guid id)
    {
        return _taskService.DeleteTaskAsync(id);
    }

    public Task<TaskItem> Complete(Guid id)
    {
        return _taskService.CompleteTaskAsync(id);
    }
}
```

- [ ] **Step 13: Write SynapseTest.Tests/SynapseTest.Tests.csproj**

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\SynapseTest.csproj" />
  </ItemGroup>
</Project>
```

- [ ] **Step 14: Write SynapseTest.Tests/TaskServiceTests.cs**

Fields typed as `ITaskService` and `TaskService` — covers **bug 2** (test reference counting). Method body calls interface method to create a CALLS edge from test code:

```csharp
namespace SynapseTest.Tests;

using SynapseTest.Services;

public class TaskServiceTests
{
    private readonly ITaskService _mockService;
    private readonly TaskService _realService;

    public TaskServiceTests(ITaskService mockService, TaskService realService)
    {
        _mockService = mockService;
        _realService = realService;
    }

    public void TestCreateTask()
    {
        _mockService.CreateTaskAsync("test", Guid.NewGuid());
    }

    public void TestCompleteTask()
    {
        _mockService.CompleteTaskAsync(Guid.NewGuid());
    }
}
```

- [ ] **Step 15: Verify the project builds**

```bash
cd tests/fixtures/SynapseTest && dotnet build
cd SynapseTest.Tests && dotnet build
```

Both should compile without errors.

- [ ] **Step 16: Commit fixture project**

```bash
git add tests/fixtures/SynapseTest/
git commit -m "refactor: replace Animal fixture with task management domain

New fixture covers controller→service call chains, multi-level DI,
abstract base classes, interface dispatch, and a test sub-project
for type impact reference counting."
```

---

## Chunk 2: Shared Test Infrastructure (conftest.py)

### Task 2: Create integration test conftest

**Files:**
- Create: `tests/integration/conftest.py`
- Delete: `tests/mcp/test_tools_integration.py`
- Delete: `tests/integration/test_graph_schema.py`

- [ ] **Step 1: Write tests/integration/conftest.py**

Session-scoped fixture that indexes the fixture project once across both test files. Provides `service` and `mcp_server` to all tests in the directory.

```python
"""
Shared fixtures for integration tests.

Requires FalkorDB on localhost:6379 and .NET SDK.
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


@pytest.fixture(scope="session")
def service():
    conn = GraphConnection.create(graph_name="synapse_integration_test")
    ensure_schema(conn)
    conn.execute("MATCH (n) DETACH DELETE n")

    svc = SynapseService(conn=conn)
    svc.index_project(FIXTURE_PATH, "csharp")

    yield svc

    conn.execute("MATCH (n) DETACH DELETE n")


@pytest.fixture(scope="session")
def mcp_server(service):
    mcp = FastMCP("synapse-test")
    register_tools(mcp, service)
    return mcp
```

- [ ] **Step 2: Delete old integration test files**

```bash
rm tests/mcp/test_tools_integration.py
rm tests/integration/test_graph_schema.py
```

Remove the `tests/mcp/` directory if empty:

```bash
rmdir tests/mcp/ 2>/dev/null || true
```

- [ ] **Step 3: Commit conftest and cleanup**

```bash
git add tests/integration/conftest.py
git rm tests/mcp/test_tools_integration.py tests/integration/test_graph_schema.py
git commit -m "refactor: add shared integration conftest, remove old test files

Session-scoped fixture indexes the task management fixture once.
Provides service and mcp_server to all integration tests."
```

---

## Chunk 3: MCP Tool Integration Tests

### Task 3: Write MCP tool integration tests

**Files:**
- Create: `tests/integration/test_mcp_tools.py`

- [ ] **Step 1: Write the test file**

All tests use `@pytest.mark.integration` and `@pytest.mark.timeout(10)` (except the indexing-dependent first test which gets `timeout(120)`).

Import helpers from conftest:

```python
"""
MCP tool integration tests.

Requires FalkorDB on localhost:6379 and .NET SDK.
Run with: pytest tests/integration/test_mcp_tools.py -v -m integration
"""
from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp import FastMCP

from tests.integration.conftest import run, content, text, result_json, FIXTURE_PATH


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
        "query": "Task", "kind": "class"
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
```

- [ ] **Step 2: Run MCP integration tests to verify they pass**

```bash
pytest tests/integration/test_mcp_tools.py -v -m integration
```

All tests should pass. If any CALLS edge tests fail (bug 1 regression), that indicates the indexer bug is still present — document which ones fail as `xfail` with a reason referencing the bug report, and file a follow-up.

- [ ] **Step 3: Commit MCP tests**

```bash
git add tests/integration/test_mcp_tools.py
git commit -m "test: add comprehensive MCP tool integration tests

29 tools covered with hybrid assertions. Includes parametrized
regression tests for bug 1 (missing CALLS edges) and bug 2
(undercounted test references in find_type_impact)."
```

---

## Chunk 4: CLI Command Integration Tests

### Task 4: Write CLI command integration tests

**Files:**
- Create: `tests/integration/test_cli_commands.py`

- [ ] **Step 1: Write the test file**

CLI tests patch `synapse.cli.app._get_service` to return the real integration service, then invoke commands via CliRunner:

```python
"""
CLI command integration tests.

Requires FalkorDB on localhost:6379 and .NET SDK.
Run with: pytest tests/integration/test_cli_commands.py -v -m integration
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from synapse.cli.app import app
from synapse.service import SynapseService
from tests.integration.conftest import FIXTURE_PATH

runner = CliRunner()


def _invoke(service: SynapseService, args: list[str]):
    """Invoke a CLI command with the integration service injected."""
    with patch("synapse.cli.app._get_service", return_value=service):
        return runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Bug 1 regression: CLI callers/callees for controller actions
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_callees_controller_create(service: SynapseService) -> None:
    result = _invoke(service, ["callees", "SynapseTest.Controllers.TaskController.Create"])
    assert result.exit_code == 0
    assert "CreateTaskAsync" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_callers_service_method(service: SynapseService) -> None:
    result = _invoke(service, ["callers", "SynapseTest.Services.TaskService.CreateTaskAsync"])
    assert result.exit_code == 0
    assert "Create" in result.output


# ---------------------------------------------------------------------------
# Relationship commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_implementations(service: SynapseService) -> None:
    result = _invoke(service, ["implementations", "SynapseTest.Services.ITaskService"])
    assert result.exit_code == 0
    assert "TaskService" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_hierarchy(service: SynapseService) -> None:
    result = _invoke(service, ["hierarchy", "SynapseTest.Models.TaskItem"])
    assert result.exit_code == 0
    assert "BaseEntity" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_trace(service: SynapseService) -> None:
    result = _invoke(service, [
        "trace",
        "SynapseTest.Controllers.TaskController.Create",
        "SynapseTest.Services.ProjectService.ValidateProjectAsync",
    ])
    assert result.exit_code == 0
    assert "Path" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_entry_points(service: SynapseService) -> None:
    result = _invoke(service, [
        "entry-points",
        "SynapseTest.Services.ProjectService.ValidateProjectAsync",
    ])
    assert result.exit_code == 0
    assert "TaskController" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_call_depth(service: SynapseService) -> None:
    result = _invoke(service, [
        "call-depth",
        "SynapseTest.Controllers.TaskController.Create",
    ])
    assert result.exit_code == 0
    assert "depth" in result.output.lower()


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_impact(service: SynapseService) -> None:
    result = _invoke(service, [
        "impact",
        "SynapseTest.Services.TaskService.CreateTaskAsync",
    ])
    assert result.exit_code == 0
    assert "TaskController" in result.output or "direct" in result.output.lower()


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_contract(service: SynapseService) -> None:
    result = _invoke(service, [
        "contract",
        "SynapseTest.Services.TaskService.CreateTaskAsync",
    ])
    assert result.exit_code == 0
    assert "ITaskService" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_type_impact(service: SynapseService) -> None:
    result = _invoke(service, [
        "type-impact",
        "SynapseTest.Services.ITaskService",
    ])
    assert result.exit_code == 0
    assert "ITaskService" in result.output


# ---------------------------------------------------------------------------
# Symbol query commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_symbol(service: SynapseService) -> None:
    result = _invoke(service, ["symbol", "SynapseTest.Services.TaskService"])
    assert result.exit_code == 0
    assert "TaskService" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_source(service: SynapseService) -> None:
    result = _invoke(service, ["source", "SynapseTest.Controllers.TaskController"])
    assert result.exit_code == 0
    assert "TaskController" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search(service: SynapseService) -> None:
    result = _invoke(service, ["search", "Task"])
    assert result.exit_code == 0
    assert "Task" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_type_refs(service: SynapseService) -> None:
    result = _invoke(service, ["type-refs", "SynapseTest.Services.ITaskService"])
    assert result.exit_code == 0
    assert "TaskController" in result.output or "ITaskService" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_dependencies(service: SynapseService) -> None:
    result = _invoke(service, ["dependencies", "SynapseTest.Controllers.TaskController"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Project-level commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_status(service: SynapseService) -> None:
    result = _invoke(service, ["status"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_query(service: SynapseService) -> None:
    result = _invoke(service, ["query", "MATCH (n:Class) RETURN n.name LIMIT 5"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_context(service: SynapseService) -> None:
    result = _invoke(service, ["context", "SynapseTest.Controllers.TaskController"])
    assert result.exit_code == 0
    assert "TaskController" in result.output


# ---------------------------------------------------------------------------
# Audit / summarize commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_audit(service: SynapseService) -> None:
    result = _invoke(service, ["audit", "untested_services"])
    assert result.exit_code == 0
    assert "untested_services" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_summarize(service: SynapseService) -> None:
    result = _invoke(service, ["summarize", "SynapseTest.Services.TaskService"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Summary subcommands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_summary_set_get_list(service: SynapseService) -> None:
    set_result = _invoke(service, [
        "summary", "set", "SynapseTest.Models.TaskItem", "A task entity."
    ])
    assert set_result.exit_code == 0

    get_result = _invoke(service, ["summary", "get", "SynapseTest.Models.TaskItem"])
    assert get_result.exit_code == 0
    assert "A task entity." in get_result.output

    list_result = _invoke(service, ["summary", "list"])
    assert list_result.exit_code == 0
    assert "TaskItem" in list_result.output
```

- [ ] **Step 2: Run CLI integration tests to verify they pass**

```bash
pytest tests/integration/test_cli_commands.py -v -m integration
```

- [ ] **Step 3: Commit CLI tests**

```bash
git add tests/integration/test_cli_commands.py
git commit -m "test: add CLI command integration tests

26 CLI commands tested via CliRunner with real indexed data.
Includes regression tests for CALLS edge visibility through CLI."
```

---

## Chunk 5: Update Unit Tests and Final Cleanup

### Task 5: Update unit tests that reference old fixture symbols

**Files:**
- Modify: `tests/unit/test_tools.py` (if it references Animal/Dog/Cat symbols)
- Modify: any other unit tests that import from or reference the old fixture

- [ ] **Step 1: Check for references to old fixture symbols in unit tests**

```bash
grep -r "IAnimal\|SynapseTest\.Dog\|SynapseTest\.Cat\|AnimalService\|Greeter\|Formatter" tests/unit/ --include="*.py" -l
```

Unit tests use mocks, so they should NOT reference fixture symbols. If any do, update them to use the new domain names. If none reference the old fixture, skip to step 3.

- [ ] **Step 2: Update any affected unit tests**

Replace old symbol names (Dog, Cat, IAnimal, AnimalService, Greeter, Formatter) with new domain equivalents (TaskItem, Project, ITaskService, TaskService, TaskController) in mock return values and assertions. The mock data is arbitrary so the specific names don't matter for correctness — just consistency.

- [ ] **Step 3: Run full unit test suite**

```bash
pytest tests/unit/ -v
```

All 153 tests should still pass. Unit tests use mocks and should be unaffected by the fixture change.

- [ ] **Step 4: Run full integration suite**

```bash
pytest tests/integration/ -v -m integration
```

Both `test_mcp_tools.py` and `test_cli_commands.py` should pass.

- [ ] **Step 5: Final commit if any cleanup was needed**

```bash
git add -u
git commit -m "chore: update unit tests for new fixture domain names"
```
