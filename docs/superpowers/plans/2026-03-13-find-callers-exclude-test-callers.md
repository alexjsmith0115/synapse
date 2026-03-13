# find_callers exclude_test_callers Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `exclude_test_callers: bool = False` to `find_callers` at all three layers so AI agents can filter out test-project callers from results.

**Architecture:** A constant regex pattern `_TEST_PATH_PATTERN` in `lookups.py` is conditionally injected as a `WHERE NOT caller.file_path =~ $test_pattern` clause into both Cypher queries (direct CALLS and via-interface dispatch). The parameter is passed as a query param (not string interpolation). The flag is threaded through `SynapseService` and the MCP tool unchanged.

**Tech Stack:** Python 3.11+, FalkorDB (`falkordb` client, supports `=~` POSIX regex), FastMCP (`mcp` library), pytest.

---

## Chunk 1: Core implementation and unit tests

### Task 1: Add failing unit tests for `exclude_test_callers`

**Files:**
- Modify: `tests/unit/test_queries.py:4` (import line)
- Modify: `tests/unit/test_queries.py:85` (append after existing `find_callers` tests)

Background: `find_callers` filtering is implemented entirely in Cypher — the `WHERE NOT caller.file_path =~ $test_pattern` clause is part of the query string sent to FalkorDB. The Python layer does not filter nodes itself. Unit tests therefore verify that (a) the correct query string is issued, and (b) the correct parameters are bound.

- [ ] **Step 1: Update the import line in `test_queries.py`**

Change line 4 from:
```python
from synapse.graph.lookups import find_callers, find_implementations, get_hierarchy, list_summarized, search_symbols, _VALID_KINDS, find_dependencies as qs_find_deps
```
To:
```python
from synapse.graph.lookups import find_callers, find_implementations, get_hierarchy, list_summarized, search_symbols, _VALID_KINDS, _TEST_PATH_PATTERN, find_dependencies as qs_find_deps
```

- [ ] **Step 2: Append 3 new failing tests after line 85 of `test_queries.py`**

```python
def test_find_callers_default_no_filter():
    """Default call must NOT inject the test-pattern parameter."""
    conn = MagicMock()
    conn.query.return_value = []
    find_callers(conn, "Svc.DoWork")
    query_str = conn.query.call_args_list[0][0][0]
    assert "$test_pattern" not in query_str


def test_find_callers_exclude_direct_early_return():
    """exclude_test_callers=True with interface dispatch off:
    - WHERE clause present in query
    - test_pattern bound to _TEST_PATH_PATTERN
    - full_name bound
    - conn.query called exactly once (early return path)
    """
    conn = MagicMock()
    conn.query.return_value = []
    find_callers(conn, "Svc.DoWork", include_interface_dispatch=False, exclude_test_callers=True)
    assert conn.query.call_count == 1
    query_str, params = conn.query.call_args[0]
    assert "WHERE NOT caller.file_path =~ $test_pattern" in query_str
    assert params["test_pattern"] == _TEST_PATH_PATTERN
    assert "full_name" in params


def test_find_callers_exclude_via_iface():
    """exclude_test_callers=True with interface dispatch on:
    both queries (direct + via-iface) must include WHERE and bind test_pattern.
    """
    caller_node = FalkorNode(node_id=1, labels=["Method"], properties={"full_name": "A.Caller"})
    conn = MagicMock()
    conn.query.side_effect = [[[caller_node]], []]
    find_callers(conn, "Svc.DoWork", include_interface_dispatch=True, exclude_test_callers=True)
    assert conn.query.call_count == 2
    for call in conn.query.call_args_list:
        query_str, params = call[0]
        assert "WHERE NOT caller.file_path =~ $test_pattern" in query_str
        assert params["test_pattern"] == _TEST_PATH_PATTERN
```

- [ ] **Step 3: Run the new tests to confirm they fail (NameError on `_TEST_PATH_PATTERN`)**

```bash
source .venv/bin/activate && pytest tests/unit/test_queries.py::test_find_callers_default_no_filter tests/unit/test_queries.py::test_find_callers_exclude_direct_early_return tests/unit/test_queries.py::test_find_callers_exclude_via_iface -v
```

Expected: 3 failures with `ImportError: cannot import name '_TEST_PATH_PATTERN'`

---

### Task 2: Implement `_TEST_PATH_PATTERN` and updated `find_callers` in `lookups.py`

**Files:**
- Modify: `src/synapse/graph/lookups.py:12` (add constant after `_VALID_KINDS`)
- Modify: `src/synapse/graph/lookups.py:46-70` (replace `find_callers` body)

- [ ] **Step 1: Add `_TEST_PATH_PATTERN` constant after `_VALID_KINDS` (after line 12)**

```python
_TEST_PATH_PATTERN = r".*[/\\][A-Za-z0-9.]*[Tt]ests?[/\\].*"
```

Place it immediately after the `_VALID_KINDS` block.

- [ ] **Step 2: Replace `find_callers` (lines 46–70) with the updated implementation**

```python
def find_callers(
    conn: GraphConnection,
    method_full_name: str,
    include_interface_dispatch: bool = True,
    exclude_test_callers: bool = False,
) -> list[dict]:
    if exclude_test_callers:
        direct = conn.query(
            "MATCH (caller:Method)-[:CALLS]->(m:Method {full_name: $full_name}) "
            "WHERE NOT caller.file_path =~ $test_pattern RETURN caller",
            {"full_name": method_full_name, "test_pattern": _TEST_PATH_PATTERN},
        )
    else:
        direct = conn.query(
            "MATCH (caller:Method)-[:CALLS]->(m:Method {full_name: $full_name}) RETURN caller",
            {"full_name": method_full_name},
        )
    if not include_interface_dispatch:
        return [r[0] for r in direct]
    if exclude_test_callers:
        via_iface = conn.query(
            "MATCH (caller:Method)-[:CALLS]->(im:Method)"
            "<-[:IMPLEMENTS]-(m:Method {full_name: $full_name}) "
            "WHERE NOT caller.file_path =~ $test_pattern RETURN caller",
            {"full_name": method_full_name, "test_pattern": _TEST_PATH_PATTERN},
        )
    else:
        via_iface = conn.query(
            "MATCH (caller:Method)-[:CALLS]->(im:Method)"
            "<-[:IMPLEMENTS]-(m:Method {full_name: $full_name}) RETURN caller",
            {"full_name": method_full_name},
        )
    seen = set()
    result = []
    for row in direct + via_iface:
        node = row[0]
        key = node.id if hasattr(node, "id") else node.get("full_name")
        if key not in seen:
            seen.add(key)
            result.append(node)
    return result
```

- [ ] **Step 3: Run all `find_callers` unit tests — all 6 must pass**

```bash
source .venv/bin/activate && pytest tests/unit/test_queries.py -k "find_callers" -v
```

Expected: 6 passed (3 existing + 3 new)

- [ ] **Step 4: Run the full unit suite to check for regressions**

```bash
source .venv/bin/activate && pytest tests/unit/ -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add src/synapse/graph/lookups.py tests/unit/test_queries.py
git commit -m "feat: add exclude_test_callers param to find_callers graph query"
```

---

### Task 3: Propagate parameter through `SynapseService` and MCP tool

**Files:**
- Modify: `src/synapse/service.py:142-144`
- Modify: `src/synapse/mcp/tools.py:83-94`

No new unit tests are needed here — both layers are thin pass-throughs and the integration test covers the full stack.

- [ ] **Step 1: Update `SynapseService.find_callers` (lines 142–144 of `service.py`)**

Replace:
```python
def find_callers(self, method_full_name: str, include_interface_dispatch: bool = True) -> list[dict]:
    method_full_name = self._resolve(method_full_name)
    return [_p(item) for item in find_callers(self._conn, method_full_name, include_interface_dispatch)]
```
With:
```python
def find_callers(self, method_full_name: str, include_interface_dispatch: bool = True, exclude_test_callers: bool = False) -> list[dict]:
    method_full_name = self._resolve(method_full_name)
    return [_p(item) for item in find_callers(self._conn, method_full_name, include_interface_dispatch, exclude_test_callers)]
```

- [ ] **Step 2: Update the MCP tool `find_callers` (lines 83–94 of `tools.py`)**

Note: these lines are indented 4 spaces because they live inside the `register_tools(mcp, service)` function.

Replace:
```python
    @mcp.tool()
    def find_callers(
        method_full_name: str,
        include_interface_dispatch: bool = True,
    ) -> list[dict]:
        """Find methods that call the given method.

        By default, includes callers that invoke this method through an interface
        (common in C# DI codebases). Set include_interface_dispatch=False for
        direct CALLS edges only.
        """
        return service.find_callers(method_full_name, include_interface_dispatch)
```
With:
```python
    @mcp.tool()
    def find_callers(
        method_full_name: str,
        include_interface_dispatch: bool = True,
        exclude_test_callers: bool = False,
    ) -> list[dict]:
        """Find methods that call the given method.

        By default, includes callers that invoke this method through an interface
        (common in C# DI codebases). Set include_interface_dispatch=False for
        direct CALLS edges only.

        Set exclude_test_callers=True to omit callers from test projects
        (files whose path contains a directory segment ending in Test, Tests,
        test, or tests — e.g. MyApp.Tests/, tests/, IntegrationTests/).
        """
        return service.find_callers(method_full_name, include_interface_dispatch, exclude_test_callers)
```

- [ ] **Step 3: Run unit suite to confirm no regressions**

```bash
source .venv/bin/activate && pytest tests/unit/ -v
```

Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add src/synapse/service.py src/synapse/mcp/tools.py
git commit -m "feat: thread exclude_test_callers through service and MCP tool layers"
```

---

### Task 4: Update fixture and add integration test

**Files:**
- Modify: `tests/fixtures/SynapseTest/SynapseTest.Tests/TaskServiceTests.cs`
- Modify: `tests/integration/test_mcp_tools.py`

Background: The integration test needs a real CALLS edge from the test project to be non-vacuous. The existing `_mockService.CreateTaskAsync()` calls are via interface and may not be indexed. Adding a direct call on `_realService` (typed as `TaskService`, a concrete type) guarantees the LSP resolves it to `TaskService.CreateTaskAsync`, creating the needed CALLS edge.

- [ ] **Step 1: Update `TaskServiceTests.TestCreateTask` in the fixture**

Replace:
```csharp
public void TestCreateTask()
{
    _mockService.CreateTaskAsync("test", Guid.NewGuid());
}
```
With:
```csharp
public void TestCreateTask()
{
    _mockService.CreateTaskAsync("test", Guid.NewGuid());
    _realService.CreateTaskAsync("integration", Guid.NewGuid()); // direct call — ensures CALLS edge
}
```

- [ ] **Step 2: Add the integration test to `test_mcp_tools.py`**

Add this test after the Bug 2 regression block (after line 88):

```python
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
```

Also add `SynapseService` to the imports at the top of `test_mcp_tools.py`, after the existing `from tests.integration.conftest import ...` line:
```python
from synapse.service import SynapseService
```

- [ ] **Step 3: Commit fixture and integration test**

```bash
git add tests/fixtures/SynapseTest/SynapseTest.Tests/TaskServiceTests.cs tests/integration/test_mcp_tools.py
git commit -m "test: add integration test for find_callers exclude_test_callers"
```

- [ ] **Step 4 (requires FalkorDB + .NET SDK): Run integration tests to verify**

Start FalkorDB if not running:
```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb:latest
```

Run:
```bash
source .venv/bin/activate && pytest tests/integration/test_mcp_tools.py::test_find_callers_excludes_test_callers -v -m integration
```

Expected: PASSED. If the non-vacuous assertion fails (no test callers in `all_callers`), the direct call in `TaskServiceTests.TestCreateTask` was not indexed — investigate by running `service.find_callers("SynapseTest.Services.TaskService.CreateTaskAsync")` directly in a Python shell against a live indexed graph.
