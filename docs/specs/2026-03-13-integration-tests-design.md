# Integration Tests Redesign — Spec

**Date:** 2026-03-13
**Goal:** Replace the existing minimal fixture and integration tests with a richer C# fixture project and comprehensive integration tests covering all 29 MCP tools and 26 CLI commands.

## Motivation

- Current fixture (`SynapseTest`) is too minimal — 7 .cs files with a simple Animal hierarchy
- Missing coverage for controller→service call chains, multi-level DI, async patterns
- 9 newer MCP tools have no integration tests (`trace_call_chain`, `find_entry_points`, `get_call_depth`, `analyze_change_impact`, `find_interface_contract`, `find_type_impact`, `audit_architecture`, `summarize_from_graph`, `get_schema`)
- CLI commands have no integration tests (only unit tests with mocks)
- Bug report (docs/2026-03-13_synapse-bugs.md) identified two issues that must be regression-tested:
  1. Missing CALLS edges for some controller action methods
  2. `find_type_impact` undercounts test references for mock targets

## Fixture Project: `tests/fixtures/SynapseTest/`

Task management domain. Two .csproj projects.

### Structure

```
tests/fixtures/SynapseTest/
├── SynapseTest.csproj                  # net8.0 class library
├── Models/
│   ├── BaseEntity.cs                   # abstract class (Id, CreatedAt, _createdBy field)
│   ├── TaskItem.cs                     # inherits BaseEntity (Title, IsComplete, ProjectId, Project nav prop)
│   └── Project.cs                      # inherits BaseEntity (Name, ICollection<TaskItem> Tasks)
├── Services/
│   ├── ITaskService.cs                 # 6 async methods
│   ├── TaskService.cs                  # implements ITaskService, injects IProjectService
│   ├── IProjectService.cs             # 2 async methods
│   └── ProjectService.cs              # implements IProjectService
├── Controllers/
│   ├── BaseController.cs              # abstract (GetUserId, ConvertToGuid helpers)
│   └── TaskController.cs             # inherits BaseController, injects ITaskService, 6 action methods
└── SynapseTest.Tests/
    ├── SynapseTest.Tests.csproj       # references SynapseTest.csproj, no test framework
    └── TaskServiceTests.cs            # fields of type ITaskService, TaskService; method bodies call interface methods

```

### Patterns Covered

| Pattern | Where | What it exercises |
|---|---|---|
| Abstract base class | BaseEntity → TaskItem, Project | INHERITS edges, `get_hierarchy` |
| Controller inheritance | BaseController → TaskController | INHERITS edges |
| Interface + implementation | ITaskService → TaskService, IProjectService → ProjectService | IMPLEMENTS edges, `find_implementations` |
| Constructor DI (interface field) | TaskController(ITaskService), TaskService(IProjectService) | TYPE_REF edges, `find_dependencies` |
| Interface dispatch calls | TaskController calls `_taskService.Method()` | CALLS edges (bug 1 regression) |
| Service-to-service calls | TaskService calls `_projectService.ValidateProjectAsync()` | Multi-level call chains |
| Intra-class calls | ProjectService.ValidateProjectAsync calls GetProjectAsync | CALLS within same class |
| Navigation properties | TaskItem.Project, Project.Tasks | TYPE_REF edges |
| Protected fields | BaseEntity._createdBy | Field node coverage |
| Async method signatures | Task<T>, Task<T?>, Task<List<T>> | Method signature indexing |
| Test project references | TaskServiceTests references ITaskService, TaskService | `find_type_impact` test counting (bug 2) |

### Bug Regression Coverage

**Bug 1 — Missing CALLS edges:** TaskController has 6 action methods (Create, Get, List, Update, Delete, Complete), each calling the corresponding ITaskService method via `_taskService`. Tests assert every one of these 6 CALLS edges exists.

**Bug 2 — Undercounted test references:** TaskServiceTests has fields typed as ITaskService and TaskService. `find_type_impact("ITaskService")` must return `test_count > 0`.

## Test Structure

All integration tests in `tests/integration/`, sharing a module-scoped indexed fixture via conftest.py.

### `tests/integration/conftest.py`

- Module-scoped fixture indexes fixture project into FalkorDB once
- Provides: `service` (SynapseService), `mcp_server` (FastMCP), `cli_runner` (Typer CliRunner)
- Teardown: `delete_project`
- FastMCP helpers: `_content()`, `_text()`, `_json()` for 1.26 compatibility

### `tests/integration/test_mcp_tools.py`

29 MCP tools. Three assertion categories:

#### Exact assertions — bug regressions

| Test | Assertion |
|---|---|
| `test_controller_calls_edges` | Each of 6 TaskController actions has CALLS edge to corresponding ITaskService method |
| `test_find_type_impact_counts_test_refs` | `find_type_impact("ITaskService")` returns `test_count > 0` |
| `test_trace_call_chain` | Path exists from `TaskController.Create` → `ProjectService.ValidateProjectAsync` |
| `test_find_entry_points` | `TaskController.Create` is an entry point for `ValidateProjectAsync` |
| `test_analyze_change_impact` | `TaskController.Create` is in callers of `TaskService.CreateTaskAsync` |

#### Exact assertions — core correctness

| Test | Assertion |
|---|---|
| `test_get_symbol` | Known symbol returns correct `full_name`, `kind`, `file_path` |
| `test_get_symbol_source` | Returns source code containing expected text |
| `test_find_implementations` | `ITaskService` → `[TaskService]`, `IProjectService` → `[ProjectService]` |
| `test_find_callers` | `TaskService.CreateTaskAsync` called by `TaskController.Create` |
| `test_find_callees` | `TaskController.Create` calls `CreateTaskAsync` |
| `test_get_hierarchy` | `TaskController` hierarchy includes `BaseController`; `TaskItem` includes `BaseEntity` |
| `test_find_type_references` | `ITaskService` referenced by `TaskController` and `TaskServiceTests` |
| `test_find_dependencies` | `TaskController` depends on `ITaskService` |
| `test_find_interface_contract` | `TaskService.CreateTaskAsync` satisfies `ITaskService` contract |

#### Structural assertions — coverage

| Test | Assertion |
|---|---|
| `test_list_projects` | Non-empty, contains fixture path |
| `test_get_index_status` | Returns dict with expected keys |
| `test_search_symbols` | `search("Task", kind="class")` returns results |
| `test_get_schema` | Returns dict with `node_labels` and `relationship_types` |
| `test_execute_query` | Simple MATCH returns results |
| `test_execute_mutating_query_blocked` | CREATE/DELETE/SET Cypher raises error |
| `test_set_get_summary` | Round-trip set then get |
| `test_list_summarized` | After set_summary, symbol appears in list |
| `test_get_context_for` | Returns non-empty string |
| `test_audit_architecture` | Returns dict for "untested_services" |
| `test_summarize_from_graph` | Returns dict for known class |
| `test_get_call_depth` | Returns reachable methods from starting method |
| `test_watch_unwatch` | Both succeed without error |

### `tests/integration/test_cli_commands.py`

CLI commands via Typer CliRunner. Mirrors MCP tool coverage.

#### Exact assertions

| Test | Assertion |
|---|---|
| `test_callers` | Output contains `TaskController.Create` |
| `test_callees` | Output contains `CreateTaskAsync` |
| `test_implementations` | Output contains `TaskService` |
| `test_hierarchy` | Output contains `BaseEntity` |
| `test_trace` | Output shows path |
| `test_entry_points` | Output contains `TaskController` |
| `test_impact` | Output contains callers |

#### Structural assertions

| Test | Assertion |
|---|---|
| `test_status` | Exit code 0, output contains fixture path |
| `test_symbol` | Exit code 0, output contains symbol name |
| `test_source` | Exit code 0, output contains method source |
| `test_search` | Exit code 0, returns results |
| `test_query` | Exit code 0 |
| `test_type_refs` | Exit code 0, returns results |
| `test_dependencies` | Exit code 0 |
| `test_context` | Exit code 0 |
| `test_contract` | Exit code 0 |
| `test_type_impact` | Exit code 0 |
| `test_audit` | Exit code 0 |
| `test_summarize` | Exit code 0 |
| `test_summary_set_get_list` | Round-trip works |

### Removed Files

- `tests/mcp/test_tools_integration.py` — replaced by `tests/integration/test_mcp_tools.py`
- `tests/integration/test_graph_schema.py` — schema coverage folded into new tests

## Prerequisites

Same as current integration tests:
- FalkorDB running on localhost:6379
- .NET SDK installed (for LSP)
- `pytest -m integration` to run
