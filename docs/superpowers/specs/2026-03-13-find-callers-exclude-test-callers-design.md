# Design: `find_callers` — `exclude_test_callers` Parameter

**Date:** 2026-03-13
**Status:** Approved

---

## Problem

`find_callers` over-reports for high-fanout methods. Calling it on a method like `MeetingService.CreateMeetingAsync` returns all test methods that call it as setup — potentially dozens of incidental callers — alongside the 3-4 meaningful production callers. An AI agent or developer asking "what calls X?" wants signal, not test scaffolding noise.

---

## Goal

Add an opt-in `exclude_test_callers: bool = False` parameter to `find_callers` that filters out callers whose `file_path` matches a standard test-project path pattern.

---

## Out of Scope

- Custom/user-supplied exclude patterns (can be added later if needed)
- Adding an `is_test` property to Method nodes (premature; no other tools need it yet)
- Changes to `find_callees` or any other tool

---

## Design

### Test Path Pattern

A single module-level constant in `src/synapse/graph/lookups.py`:

```python
_TEST_PATH_PATTERN = r".*[/\\][A-Za-z0-9.]*[Tt]ests?[/\\].*"
```

The trailing separator is `[/\\]` (directory boundary only, not `.`), preventing false positives on production files named `*Tests.cs` in non-test directories.

`file_path` values in the graph are always absolute paths. Matches path segments such as:
- `/repo/MyApp.Tests/ServiceTests.cs` → match (exclude)
- `/repo/MyApp.Test/Helpers.cs` → match (exclude)
- `/repo/tests/unit/foo.cs` → match (exclude)
- `/repo/MyApp/Services/MeetingService.cs` → no match (keep)
- `/repo/src/Services/MyTests.cs` → no match (keep — filename only, not a directory segment)

### Parameter Signature

`exclude_test_callers: bool = False` is added as the last parameter at every layer. Default is `False` so existing callers are unaffected.

**`lookups.py`:**
```python
def find_callers(
    conn: GraphConnection,
    method_full_name: str,
    include_interface_dispatch: bool = True,
    exclude_test_callers: bool = False,
) -> list[dict]:
```

**`SynapseService`:**
```python
def find_callers(
    self,
    method_full_name: str,
    include_interface_dispatch: bool = True,
    exclude_test_callers: bool = False,
) -> list[dict]:
```

**MCP tool (`tools.py`):**
```python
def find_callers(
    method_full_name: str,
    include_interface_dispatch: bool = True,
    exclude_test_callers: bool = False,
) -> list[dict]:
```

### Cypher Changes

Both queries in `lookups.find_callers` conditionally include a `WHERE` clause. When `exclude_test_callers=False`, queries are identical to today (no performance impact).

When `include_interface_dispatch=False`, the existing early return (`return [r[0] for r in direct]`) is unchanged — no Python-level post-filtering is needed because the `WHERE` clause already filters the results in the query itself.

**Direct callers (exclude_test_callers=True):**
```cypher
MATCH (caller:Method)-[:CALLS]->(m:Method {full_name: $full_name})
WHERE NOT caller.file_path =~ $test_pattern
RETURN caller
```

**Via interface dispatch (exclude_test_callers=True):**
```cypher
MATCH (caller:Method)-[:CALLS]->(im:Method)<-[:IMPLEMENTS]-(m:Method {full_name: $full_name})
WHERE NOT caller.file_path =~ $test_pattern
RETURN caller
```

The `$test_pattern` parameter is bound to `_TEST_PATH_PATTERN`. Passing it as a query parameter (not string interpolation) avoids any injection risk.

When `exclude_test_callers=False`, the existing query strings are used unchanged.

### MCP Tool Docstring Addition

```
Set exclude_test_callers=True to omit callers from test projects
(files whose path contains a directory segment ending in Test, Tests,
test, or tests — e.g. MyApp.Tests/, tests/, IntegrationTests/).
```

---

## Testing

### Unit Tests (`tests/unit/`)

Four new test cases in the existing `find_callers` test file (or a new one if none exists). All use a mock `GraphConnection`.

Note: filtering happens entirely in the Cypher `WHERE` clause, not in Python. Unit tests therefore verify that correct queries and parameters are issued to the graph connection — not that the Python layer itself filters nodes (that would require an integration test).

All tests import `_TEST_PATH_PATTERN` from `synapse.graph.lookups` alongside the existing imports.

The implementation branches on `exclude_test_callers` with an `if/else` to select between two query string literals before calling `conn.query` — no string building or mutation.

1. **`test_find_callers_default_no_filter`** — `exclude_test_callers=False` (default): assert the query string passed to `conn.query` does NOT contain `$test_pattern`.

2. **`test_find_callers_exclude_direct_early_return`** — `exclude_test_callers=True`, `include_interface_dispatch=False`: assert (a) the query string contains `WHERE NOT caller.file_path =~ $test_pattern`, (b) the params dict contains `"test_pattern": _TEST_PATH_PATTERN`, (c) the params dict contains `"full_name"`, and (d) `conn.query` is called exactly once (early return path preserved).

3. **`test_find_callers_exclude_via_iface`** — `exclude_test_callers=True`, `include_interface_dispatch=True`: assert both `conn.query` calls (direct + via-interface) include the `WHERE` clause and bind `"test_pattern": _TEST_PATH_PATTERN` in the params dict.

### Integration Tests

One new test in `tests/integration/test_mcp_tools.py`.

**Fixture change:** `SynapseTest.Tests/TaskServiceTests.cs` already calls `_mockService.CreateTaskAsync()` via interface — whether this produces a CALLS edge depends on LSP resolution. To guarantee at least one resolvable CALLS edge from the test project, add a direct call on the concrete type to `TestCreateTask`:

```csharp
public void TestCreateTask()
{
    _mockService.CreateTaskAsync("test", Guid.NewGuid());
    _realService.CreateTaskAsync("integration", Guid.NewGuid()); // direct call — ensures CALLS edge
}
```

Direct calls on concrete types (`_realService` typed as `TaskService`) are reliably resolved by the LSP, creating a CALLS edge from `TaskServiceTests.TestCreateTask` → `TaskService.CreateTaskAsync`.

**`test_find_callers_excludes_test_callers`:**

1. Call `service.find_callers("SynapseTest.Services.TaskService.CreateTaskAsync")` — capture `all_callers`.
2. Call the same with `exclude_test_callers=True` — capture `filtered_callers`.
3. Assert no caller in `filtered_callers` has a `file_path` containing `SynapseTest.Tests` (core assertion — never broken by CALLS edge availability).
4. Assert `len(filtered_callers) <= len(all_callers)` (filter never adds callers).
5. Assert that `all_callers` contains at least one caller from `SynapseTest.Tests` (non-vacuous check — proves the fixture produces the noise being filtered). If this fails, the fixture's direct call needs investigation.

---

## Affected Files

| File | Change |
|------|--------|
| `src/synapse/graph/lookups.py` | Add `_TEST_PATH_PATTERN` constant; add `exclude_test_callers` param; conditionally add `WHERE` clause to both queries |
| `src/synapse/service.py` | Add `exclude_test_callers` param; pass through to `lookups.find_callers` |
| `src/synapse/mcp/tools.py` | Add `exclude_test_callers` param; pass through to `service.find_callers`; update docstring |
| `tests/unit/test_queries.py` | Add 3 new test cases (existing `find_callers` tests live here); add `_TEST_PATH_PATTERN` to imports |
| `tests/fixtures/SynapseTest/SynapseTest.Tests/TaskServiceTests.cs` | Add direct call to `_realService.CreateTaskAsync(...)` in `TestCreateTask` |
| `tests/integration/test_mcp_tools.py` | Add `test_find_callers_excludes_test_callers` |
