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
_TEST_PATH_PATTERN = r".*[/\\][A-Za-z0-9.]*[Tt]ests?[/\\.].*"
```

Matches path segments such as:
- `MyApp.Tests/ServiceTests.cs` → match (exclude)
- `MyApp.Test/Helpers.cs` → match (exclude)
- `tests/unit/foo.cs` → match (exclude)
- `MyApp/Services/MeetingService.cs` → no match (keep)

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
(files whose path contains a segment matching *Test* or *Tests*).
```

---

## Testing

### Unit Tests (`tests/unit/`)

Three new test cases in the existing `find_callers` test file (or a new one if none exists):

1. **`test_find_callers_default_includes_test_callers`** — `exclude_test_callers=False` (default): assert the query passed to `conn.query` does NOT contain `WHERE`.
2. **`test_find_callers_exclude_test_callers_direct`** — `exclude_test_callers=True`, `include_interface_dispatch=False`: assert the direct query contains `WHERE NOT caller.file_path =~ $test_pattern`.
3. **`test_find_callers_exclude_test_callers_via_iface`** — `exclude_test_callers=True`, `include_interface_dispatch=True`: assert both the direct AND via-interface queries contain the `WHERE` clause.

All tests use a mock `GraphConnection`.

### Integration Tests

No changes needed — the `SynapseTest` fixture project contains no test files, so the filter has no observable effect there.

---

## Affected Files

| File | Change |
|------|--------|
| `src/synapse/graph/lookups.py` | Add `_TEST_PATH_PATTERN` constant; add `exclude_test_callers` param; conditionally add `WHERE` clause to both queries |
| `src/synapse/service.py` | Add `exclude_test_callers` param; pass through to `lookups.find_callers` |
| `src/synapse/mcp/tools.py` | Add `exclude_test_callers` param; pass through to `service.find_callers`; update docstring |
| `tests/unit/test_find_callers.py` | Add 3 new test cases |
