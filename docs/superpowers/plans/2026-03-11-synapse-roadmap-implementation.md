# Synapse Roadmap Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the full Synapse roadmap — multi-hop call chains, impact analysis, architectural audit, summary generation, staleness detection, and short-name resolution — phased as quick wins then by priority.

**Architecture:** New query modules (`graph/traversal.py`, `graph/analysis.py`) alongside the renamed `graph/lookups.py`. Service layer delegates to query functions and handles name resolution via a shared `_resolve` helper. All new tools return structured data (dicts/lists) optimized for agentic consumption.

**Tech Stack:** Python 3.11+, FalkorDB (Cypher), FastMCP, Typer, pytest.

**Spec:** `docs/superpowers/specs/2026-03-11-synapse-roadmap-design.md`

---

## Chunk 1: Phase 0 — Foundations

### Task 1: Rename `graph/queries.py` → `graph/lookups.py`

**Files:**
- Rename: `src/synapse/graph/queries.py` → `src/synapse/graph/lookups.py`
- Modify: `src/synapse/service.py:7` (import)
- Modify: `tests/unit/graph/test_queries.py:3` (import)
- Modify: `tests/unit/test_queries.py:4` (import)

- [ ] **Step 1: Rename the file**

```bash
cd /Users/alex/Dev/mcpcontext
git mv src/synapse/graph/queries.py src/synapse/graph/lookups.py
```

- [ ] **Step 2: Update import in `service.py`**

Replace line 7 in `src/synapse/service.py`:

```python
# OLD
from synapse.graph.queries import (

# NEW
from synapse.graph.lookups import (
```

- [ ] **Step 3: Update import in `tests/unit/graph/test_queries.py`**

Replace line 3:

```python
# OLD
from synapse.graph.queries import (

# NEW
from synapse.graph.lookups import (
```

- [ ] **Step 4: Update import in `tests/unit/test_queries.py`**

Replace line 4:

```python
# OLD
from synapse.graph.queries import find_callers, find_implementations, get_hierarchy, list_summarized, search_symbols, _VALID_KINDS, find_dependencies as qs_find_deps

# NEW
from synapse.graph.lookups import find_callers, find_implementations, get_hierarchy, list_summarized, search_symbols, _VALID_KINDS, find_dependencies as qs_find_deps
```

- [ ] **Step 5: Run full unit suite to verify no broken imports**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: All 153+ tests pass.

- [ ] **Step 6: Commit**

`git mv` already staged the rename. Stage the modified import files:

```bash
git add src/synapse/service.py tests/unit/graph/test_queries.py tests/unit/test_queries.py
git commit -m "refactor: rename graph/queries.py to graph/lookups.py

Clarifies the module's role as direct symbol lookups and single-hop
relationships, making room for new traversal.py and analysis.py modules."
```

Note: `cli/app.py` does not import `graph.queries` directly (it goes through the service layer), so no change needed there.

---

### Task 2: Add `resolve_full_name` helper to `lookups.py`

**Files:**
- Modify: `src/synapse/graph/lookups.py` (add function at end of file)
- Create: `tests/unit/graph/test_resolve.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/graph/test_resolve.py`:

```python
from unittest.mock import MagicMock

from synapse.graph.lookups import resolve_full_name


def _conn(return_value: list) -> MagicMock:
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_exact_match_returns_string() -> None:
    conn = _conn([["Ns.MyClass"]])
    result = resolve_full_name(conn, "Ns.MyClass")
    assert result == "Ns.MyClass"


def test_exact_match_without_dot() -> None:
    """Symbols without namespaces (e.g. 'Animal') should exact-match first."""
    conn = _conn([["Animal"]])
    result = resolve_full_name(conn, "Animal")
    assert result == "Animal"
    # Should have tried exact match, not just suffix
    cypher = conn.query.call_args_list[0][0][0]
    assert "full_name" in cypher


def test_suffix_fallback_single_match() -> None:
    conn = MagicMock()
    # First call (exact match) returns nothing; second call (suffix) returns one match
    conn.query.side_effect = [[], [["Ns.Sub.MyClass"]]]
    result = resolve_full_name(conn, "MyClass")
    assert result == "Ns.Sub.MyClass"


def test_suffix_fallback_multiple_matches() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], [["A.MyClass"], ["B.MyClass"]]]
    result = resolve_full_name(conn, "MyClass")
    assert result == ["A.MyClass", "B.MyClass"]


def test_no_match_returns_original() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    result = resolve_full_name(conn, "NoSuchThing")
    assert result == "NoSuchThing"


def test_exact_match_skips_suffix() -> None:
    """If exact match succeeds, suffix match should not be attempted."""
    conn = _conn([["Ns.MyClass"]])
    resolve_full_name(conn, "Ns.MyClass")
    assert conn.query.call_count == 1
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/graph/test_resolve.py -v
```

Expected: FAIL — `resolve_full_name` not defined.

- [ ] **Step 3: Implement `resolve_full_name`**

Add to the end of `src/synapse/graph/lookups.py`:

```python
def resolve_full_name(conn: GraphConnection, name: str) -> str | list[str]:
    """Resolve a possibly-short symbol name to its full qualified name.

    Tries exact match first, then falls back to suffix matching.
    Returns the original name unchanged if no match is found (lets
    downstream queries fail naturally with empty results).
    """
    rows = conn.query(
        "MATCH (n {full_name: $name}) RETURN n.full_name LIMIT 1",
        {"name": name},
    )
    if rows:
        return rows[0][0]

    rows = conn.query(
        "MATCH (n) WHERE n.full_name ENDS WITH $suffix "
        "RETURN n.full_name",
        {"suffix": "." + name},
    )
    if len(rows) == 1:
        return rows[0][0]
    if len(rows) > 1:
        return [r[0] for r in rows]
    return name
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/graph/test_resolve.py -v
```

Expected: All pass.

- [ ] **Step 5: Run full unit suite**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/synapse/graph/lookups.py tests/unit/graph/test_resolve.py
git commit -m "feat: add resolve_full_name helper for short-name resolution

Tries exact match first, falls back to suffix matching. Returns the
original name on no match. Multiple matches return a list for the
caller to surface as 'did you mean?' options."
```

---

### Task 3: Wire `resolve_full_name` into service layer

**Files:**
- Modify: `src/synapse/service.py` (add `_resolve` method, wire into read methods)
- Modify: `tests/unit/test_service.py` (if exists, add resolution tests)
- Create: `tests/unit/test_service_resolve.py` (if no existing service test file)

- [ ] **Step 1: Check for existing service tests**

```bash
ls tests/unit/test_service*.py 2>/dev/null || echo "none"
```

- [ ] **Step 2: Write failing test**

Create `tests/unit/test_service_resolve.py`:

```python
from unittest.mock import MagicMock, patch

from synapse.service import SynapseService


def _make_service() -> tuple[SynapseService, MagicMock]:
    conn = MagicMock()
    service = SynapseService(conn)
    return service, conn


def test_resolve_single_match_returns_string() -> None:
    service, conn = _make_service()
    # First query: resolve_full_name exact match
    # Second query: get_symbol returns a FalkorDB Node-like result
    node = MagicMock()
    node.properties = {"full_name": "Ns.MyClass", "name": "MyClass", "kind": "class"}
    node.labels = ["Class"]
    conn.query.side_effect = [
        [["Ns.MyClass"]],  # exact match in resolve_full_name
        [[node]],  # get_symbol query returns a node
    ]
    result = service.get_symbol("MyClass")
    assert result is not None
    assert result["full_name"] == "Ns.MyClass"


def test_resolve_ambiguous_raises() -> None:
    service, conn = _make_service()
    conn.query.side_effect = [
        [],  # exact match fails
        [["A.MyClass"], ["B.MyClass"]],  # suffix match returns multiple
    ]
    import pytest
    with pytest.raises(ValueError, match="Ambiguous"):
        service.get_symbol("MyClass")


def test_set_summary_does_not_resolve() -> None:
    """Write operations must not go through resolution."""
    service, conn = _make_service()
    conn.query.return_value = []
    conn.execute.return_value = None
    service.set_summary("ShortName", "some content")
    # resolve_full_name uses conn.query; set_summary should not trigger any query calls
    # (only conn.execute for the MERGE/SET)
    query_calls = conn.query.call_args_list
    assert len(query_calls) == 0, "set_summary should not call resolve_full_name"
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
pytest tests/unit/test_service_resolve.py -v
```

Expected: FAIL — `_resolve` method doesn't exist yet, `get_symbol` doesn't call it.

- [ ] **Step 4: Add `_resolve` to `SynapseService`**

First, add `resolve_full_name` to the top-level import from `synapse.graph.lookups` in `service.py` (the existing import block at line 7):

```python
from synapse.graph.lookups import (
    # ... existing imports ...
    resolve_full_name,
)
```

Then add the method after the constructor (after line 37 in `service.py`):

```python
    def _resolve(self, name: str) -> str:
        """Resolve a possibly-short name to a full qualified name.

        Raises ValueError if the name is ambiguous (matches multiple symbols).
        """
        result = resolve_full_name(self._conn, name)
        if isinstance(result, list):
            options = ", ".join(result[:10])
            raise ValueError(
                f"Ambiguous name '{name}' — matches: {options}. "
                "Use the fully qualified name."
            )
        return result
```

- [ ] **Step 5: Wire `_resolve` into read methods**

Update the following methods in `service.py` to call `self._resolve(...)` on their name parameter before delegating:

```python
    def get_symbol(self, full_name: str) -> dict | None:
        full_name = self._resolve(full_name)
        # ... existing code

    def find_implementations(self, interface_name: str) -> list[dict]:
        interface_name = self._resolve(interface_name)
        # ... existing code

    def find_callers(self, method_full_name: str, include_interface_dispatch: bool = True) -> list[dict]:
        method_full_name = self._resolve(method_full_name)
        # ... existing code

    def find_callees(self, method_full_name: str) -> list[dict]:
        method_full_name = self._resolve(method_full_name)
        # ... existing code

    def get_hierarchy(self, class_name: str) -> dict:
        class_name = self._resolve(class_name)
        # ... existing code

    def find_type_references(self, full_name: str) -> list[dict]:
        full_name = self._resolve(full_name)
        # ... existing code

    def find_dependencies(self, full_name: str, depth: int = 1) -> list[dict]:
        full_name = self._resolve(full_name)
        # ... existing code

    def get_summary(self, full_name: str) -> str | None:
        full_name = self._resolve(full_name)
        # ... existing code

    def get_symbol_source(self, full_name: str, include_class_signature: bool = False) -> str | None:
        full_name = self._resolve(full_name)
        # ... existing code

    def get_context_for(self, full_name: str) -> str | None:
        full_name = self._resolve(full_name)
        # ... existing code
```

Do **NOT** add `_resolve` to: `set_summary`, `remove_summary`, `list_summarized`, `list_projects`, `get_index_status`, `execute_query`, `search_symbols`.

- [ ] **Step 6: Run tests — verify they pass**

```bash
pytest tests/unit/test_service_resolve.py -v
```

Expected: All pass.

- [ ] **Step 7: Fix existing service tests that break due to `_resolve`**

After wiring `_resolve` into read methods, existing tests that mock `conn.query.return_value` with a single response will break — the first `conn.query` call is now consumed by `resolve_full_name` instead of the intended query. Check `tests/unit/test_service.py` (if it exists) and any other service-level tests.

For each broken test, update the mock to provide an extra response for the resolution query:

```python
# Before (single response):
conn.query.return_value = [[node]]

# After (resolution + actual query):
conn.query.side_effect = [
    [["Ns.FullName"]],  # resolve_full_name exact match
    [[node]],           # actual query
]
```

Alternatively, if the test already passes the full qualified name AND that exact name exists in the mock's first response, it may still work. Run the tests first and fix only what breaks.

- [ ] **Step 8: Run full unit suite**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: All pass.

- [ ] **Step 9: Commit**

```bash
git add src/synapse/service.py tests/unit/test_service_resolve.py
git commit -m "feat: wire short-name resolution into all read service methods

Adds _resolve() helper to SynapseService that calls resolve_full_name
before delegating to query functions. Raises ValueError for ambiguous
names. Write operations (set_summary) bypass resolution."
```

---

## Chunk 2: Phase 1 — Quick Wins

### Task 4: Auto-surface summaries in `get_context_for`

**Files:**
- Modify: `src/synapse/service.py:174-227` (`get_context_for` method)
- Modify: `tests/unit/test_service_resolve.py` or create `tests/unit/test_context_summaries.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_service_resolve.py` (or create new test file):

```python
def test_get_context_for_surfaces_summaries() -> None:
    service, conn = _make_service()

    # Mock resolve_full_name exact match
    # Mock get_symbol to return a node
    # Mock get_symbol_source_info for source retrieval
    # Mock get_summary to return content for the symbol
    from unittest.mock import patch

    with patch.object(service, "get_symbol_source", return_value="class Foo {}"):
        with patch("synapse.service.get_symbol") as mock_sym:
            mock_sym.return_value = {"full_name": "Ns.Foo", "name": "Foo"}
            with patch("synapse.service.get_containing_type", return_value=None):
                with patch("synapse.service.get_summary") as mock_summary:
                    mock_summary.return_value = "Foo handles business logic."
                    with patch("synapse.service.resolve_full_name", return_value="Ns.Foo"):
                        result = service.get_context_for("Ns.Foo")

    assert "Foo handles business logic." in result
    assert "## Summaries" in result
```

- [ ] **Step 2: Run test — verify it fails**

```bash
pytest tests/unit/test_service_resolve.py::test_get_context_for_surfaces_summaries -v
```

Expected: FAIL — `get_context_for` doesn't include summaries section yet.

- [ ] **Step 3: Add summary surfacing to `get_context_for`**

In `src/synapse/service.py`, add before the final `return` in `get_context_for` (before line 227):

```python
        # Surface any existing summaries for the symbol and its containing type/interfaces
        summary_entries: list[str] = []
        sym_summary = get_summary(self._conn, full_name)
        if sym_summary:
            summary_entries.append(f"**{full_name}:** {sym_summary}")
        if parent:
            parent_fn = _p(parent)["full_name"]
            parent_summary = get_summary(self._conn, parent_fn)
            if parent_summary:
                summary_entries.append(f"**{parent_fn}:** {parent_summary}")
            for iface in get_implemented_interfaces(self._conn, parent_fn):
                iface_fn = _p(iface)["full_name"]
                iface_summary = get_summary(self._conn, iface_fn)
                if iface_summary:
                    summary_entries.append(f"**{iface_fn}:** {iface_summary}")
        else:
            # If the symbol itself is a class, check its own interfaces
            own_interfaces = get_implemented_interfaces(self._conn, full_name)
            for iface in own_interfaces:
                iface_fn = _p(iface)["full_name"]
                iface_summary = get_summary(self._conn, iface_fn)
                if iface_summary:
                    summary_entries.append(f"**{iface_fn}:** {iface_summary}")
        if summary_entries:
            sections.append("## Summaries\n\n" + "\n\n".join(summary_entries))
```

Note: `parent` is already computed earlier in the method. When `parent` is None (the symbol itself is a class/interface), we check its own implemented interfaces for summaries. When `parent` exists, we check the parent's interfaces (already computed above — this is a second call but FalkorDB reads are fast).

- [ ] **Step 4: Run test — verify it passes**

```bash
pytest tests/unit/test_service_resolve.py::test_get_context_for_surfaces_summaries -v
```

Expected: PASS.

- [ ] **Step 5: Run full unit suite**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/synapse/service.py tests/unit/test_service_resolve.py
git commit -m "feat: auto-surface summaries in get_context_for

When summaries exist for the queried symbol, its containing type, or
its implemented interfaces, they are included as a Summaries section
in the context output."
```

---

### Task 5: Add staleness detection

**Files:**
- Modify: `src/synapse/graph/lookups.py` (add `check_staleness` function)
- Modify: `src/synapse/service.py` (add `_check_staleness` helper, wire into key methods)
- Create: `tests/unit/graph/test_staleness.py`

- [ ] **Step 1: Write failing tests for `check_staleness`**

Create `tests/unit/graph/test_staleness.py`:

```python
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from synapse.graph.lookups import check_staleness


def _conn(return_value: list) -> MagicMock:
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_check_staleness_stale_file() -> None:
    """File modified after last indexing should be stale."""
    indexed_at = "2026-03-11T10:00:00+00:00"
    conn = _conn([[indexed_at, "/proj/Foo.cs"]])
    # File was modified at 11:00, indexed at 10:00 → stale
    with patch("synapse.graph.lookups.os.path.getmtime", return_value=datetime(2026, 3, 11, 11, 0, tzinfo=timezone.utc).timestamp()):
        with patch("synapse.graph.lookups.os.path.exists", return_value=True):
            result = check_staleness(conn, "/proj/Foo.cs")

    assert result is not None
    assert result["is_stale"] is True


def test_check_staleness_fresh_file() -> None:
    """File not modified after indexing should not be stale."""
    indexed_at = "2026-03-11T12:00:00+00:00"
    conn = _conn([[indexed_at, "/proj/Foo.cs"]])
    # File was modified at 10:00, indexed at 12:00 → fresh
    with patch("synapse.graph.lookups.os.path.getmtime", return_value=datetime(2026, 3, 11, 10, 0, tzinfo=timezone.utc).timestamp()):
        with patch("synapse.graph.lookups.os.path.exists", return_value=True):
            result = check_staleness(conn, "/proj/Foo.cs")

    assert result is not None
    assert result["is_stale"] is False


def test_check_staleness_file_not_in_graph() -> None:
    conn = _conn([])
    result = check_staleness(conn, "/proj/Unknown.cs")
    assert result is None


def test_check_staleness_file_deleted_from_disk() -> None:
    """If the file no longer exists on disk, it cannot be stale."""
    conn = _conn([["2026-03-11T10:00:00+00:00", "/proj/Gone.cs"]])
    with patch("synapse.graph.lookups.os.path.exists", return_value=False):
        result = check_staleness(conn, "/proj/Gone.cs")
    assert result is None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/graph/test_staleness.py -v
```

Expected: FAIL — `check_staleness` not defined.

- [ ] **Step 3: Implement `check_staleness`**

Add to `src/synapse/graph/lookups.py`:

```python
import os
from datetime import datetime, timezone


def check_staleness(conn: GraphConnection, file_path: str) -> dict | None:
    """Check if a file's graph data is stale relative to disk.

    Compares the stored last_indexed ISO timestamp on the File node against
    the file's mtime on disk.

    NOTE: This checks only the queried file. Dependent files (files that
    IMPORT this one) may also be stale if this file's exports changed. Full
    dependent re-indexing is a future enhancement — see
    docs/plans/synapse-roadmap.md section 4. The watcher would need to:
    (1) query IMPORTS edges to find dependents, (2) re-index those files,
    (3) handle cycles and depth limits. The current approach prioritizes
    fast, local staleness detection over transitive correctness.
    """
    rows = conn.query(
        "MATCH (f:File {path: $path}) RETURN f.last_indexed, f.path",
        {"path": file_path},
    )
    if not rows:
        return None

    last_indexed_str = rows[0][0]
    if not last_indexed_str:
        return None

    if not os.path.exists(file_path):
        return None

    last_indexed = datetime.fromisoformat(last_indexed_str)
    last_modified = datetime.fromtimestamp(os.path.getmtime(file_path), tz=timezone.utc)
    is_stale = last_modified > last_indexed

    return {
        "file_path": file_path,
        "last_indexed": last_indexed_str,
        "last_modified": last_modified.isoformat(),
        "is_stale": is_stale,
    }
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/graph/test_staleness.py -v
```

Expected: All pass.

- [ ] **Step 5: Wire staleness warnings into service layer**

Add a helper to `src/synapse/service.py`:

```python
    def _staleness_warning(self, full_name: str) -> str | None:
        """Return a warning string if the symbol's file is stale, else None."""
        source_info = get_symbol_source_info(self._conn, full_name)
        if not source_info or not source_info.get("file_path"):
            return None
        staleness = check_staleness(self._conn, source_info["file_path"])
        if staleness and staleness["is_stale"]:
            return (
                f"Warning: {staleness['file_path']} was modified after last indexing. "
                "Results may be outdated. Run watch_project or re-index to refresh."
            )
        return None
```

Add the import at the top of `service.py`:

```python
from synapse.graph.lookups import check_staleness
```

**Staleness warnings are added in the MCP tool layer, NOT the service layer.** This avoids breaking internal service-to-service calls (e.g., `get_context_for` calls `self.find_callees()` and iterates the result as a list; `summarize_from_graph` calls `self.find_dependencies()` the same way). The service layer's `_staleness_warning` helper is still on the service for convenience, but only MCP tools call it.

The `_staleness_warning` helper stays on the service (it needs `self._conn`), but service methods do NOT call it. Instead, MCP tools in `tools.py` call `service._staleness_warning(full_name)` and append the result:

In `src/synapse/mcp/tools.py`, update dict-returning tools to include staleness. Example for `get_symbol`:

```python
    @mcp.tool()
    def get_symbol(full_name: str) -> dict | None:
        """Get a symbol node by full name (supports short names)."""
        result = service.get_symbol(full_name)
        if result:
            warning = service._staleness_warning(full_name)
            if warning:
                result["_staleness_warning"] = warning
        return result
```

Apply the same pattern to: `get_hierarchy`, `get_context_for`. For list-returning tools (`find_callers`, `find_callees`, `find_type_references`, `find_dependencies`), skip staleness warnings — the service return type stays `list[dict]` unchanged.

**File path matching note:** `_staleness_warning` calls `get_symbol_source_info` which reads `n.file_path` from symbol nodes, then passes that path to `check_staleness` which queries `(f:File {path: $path})`. Both store absolute paths set during indexing from the same source (`symbol.file_path`), so they will match.

- [ ] **Step 6: Run full unit suite**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add src/synapse/graph/lookups.py src/synapse/service.py tests/unit/graph/test_staleness.py
git commit -m "feat: staleness detection with warnings in tool results

Adds check_staleness() that compares File node last_indexed against
disk mtime. MCP tools append _staleness_warning to dict results when
the queried symbol's file has been modified since indexing. Staleness
is surfaced at the tool layer to avoid breaking internal service calls."
```

---

## Chunk 3: Phase 2 — Multi-Hop Call Chain Tools

### Task 6: Create `graph/traversal.py` with `trace_call_chain`

**Files:**
- Create: `src/synapse/graph/traversal.py`
- Create: `tests/unit/graph/test_traversal.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/graph/test_traversal.py`:

```python
from unittest.mock import MagicMock

from synapse.graph.traversal import trace_call_chain


def _conn(return_value: list) -> MagicMock:
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_trace_call_chain_returns_paths() -> None:
    conn = _conn([[["A.M1", "A.M2", "A.M3"]]])
    result = trace_call_chain(conn, "A.M1", "A.M3")
    assert result["paths"] == [["A.M1", "A.M2", "A.M3"]]
    assert result["start"] == "A.M1"
    assert result["end"] == "A.M3"


def test_trace_call_chain_no_path() -> None:
    conn = _conn([])
    result = trace_call_chain(conn, "A.M1", "B.M2")
    assert result["paths"] == []


def test_trace_call_chain_depth_clamped() -> None:
    conn = _conn([])
    result = trace_call_chain(conn, "A.M1", "A.M2", max_depth=20)
    # Depth should be clamped to 10
    cypher = conn.query.call_args[0][0]
    assert "*1..10" in cypher


def test_trace_call_chain_depth_in_cypher() -> None:
    conn = _conn([])
    trace_call_chain(conn, "A.M1", "A.M2", max_depth=4)
    cypher = conn.query.call_args[0][0]
    assert "*1..4" in cypher
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/graph/test_traversal.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `trace_call_chain`**

Create `src/synapse/graph/traversal.py`:

```python
"""Multi-hop call chain traversal queries.

These queries follow CALLS edges across multiple hops. FalkorDB does not
support parameterized variable-length relationship bounds, so the depth
integer is inlined into the Cypher string after validation (must be int,
clamped 1-10).
"""

from synapse.graph.connection import GraphConnection


def _clamp_depth(depth: int, max_allowed: int = 10) -> int:
    return max(1, min(int(depth), max_allowed))


def trace_call_chain(
    conn: GraphConnection,
    start: str,
    end: str,
    max_depth: int = 6,
) -> dict:
    """Find all call paths between two methods.

    Returns up to 10 paths, each a list of full_names from start to end.
    """
    depth = _clamp_depth(max_depth)
    rows = conn.query(
        f"MATCH p=(s:Method)-[:CALLS*1..{depth}]->(e:Method) "
        "WHERE s.full_name = $start AND e.full_name = $end "
        "RETURN [n in nodes(p) | n.full_name] AS path "
        "LIMIT 10",
        {"start": start, "end": end},
    )
    return {
        "paths": [r[0] for r in rows],
        "start": start,
        "end": end,
        "max_depth": depth,
    }
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/graph/test_traversal.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/synapse/graph/traversal.py tests/unit/graph/test_traversal.py
git commit -m "feat: add trace_call_chain to graph/traversal.py

Finds all call paths between two methods up to N hops (clamped 1-10).
Depth is inlined into Cypher since FalkorDB doesn't support parameterized
variable-length bounds."
```

---

### Task 7: Add `find_entry_points` to `traversal.py`

**Files:**
- Modify: `src/synapse/graph/traversal.py`
- Modify: `tests/unit/graph/test_traversal.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/graph/test_traversal.py`:

```python
from synapse.graph.traversal import find_entry_points


def test_find_entry_points_returns_paths() -> None:
    conn = _conn([[["Controller.Action", "Svc.Do", "Repo.Save"]]])
    result = find_entry_points(conn, "Repo.Save")
    assert len(result["entry_points"]) == 1
    assert result["entry_points"][0]["entry"] == "Controller.Action"
    assert result["entry_points"][0]["path"] == ["Controller.Action", "Svc.Do", "Repo.Save"]
    assert result["target"] == "Repo.Save"


def test_find_entry_points_empty() -> None:
    conn = _conn([])
    result = find_entry_points(conn, "Orphan.Method")
    assert result["entry_points"] == []
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/graph/test_traversal.py::test_find_entry_points_returns_paths -v
```

Expected: FAIL — `find_entry_points` not defined.

- [ ] **Step 3: Implement `find_entry_points`**

Add to `src/synapse/graph/traversal.py`:

```python
def find_entry_points(
    conn: GraphConnection,
    method: str,
    max_depth: int = 8,
) -> dict:
    """Walk backwards to find root callers with no incoming CALLS edges.

    Returns up to 20 paths, each with the entry point and full path to target.
    """
    depth = _clamp_depth(max_depth)
    rows = conn.query(
        f"MATCH p=(entry:Method)-[:CALLS*1..{depth}]->(target:Method {{full_name: $method}}) "
        "WHERE NOT ()-[:CALLS]->(entry) "
        "RETURN [n in nodes(p) | n.full_name] AS path "
        "LIMIT 20",
        {"method": method},
    )
    return {
        "entry_points": [
            {"entry": r[0][0], "path": r[0]}
            for r in rows
        ],
        "target": method,
        "max_depth": depth,
    }
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/graph/test_traversal.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/synapse/graph/traversal.py tests/unit/graph/test_traversal.py
git commit -m "feat: add find_entry_points to graph/traversal.py

Walks backwards from a method to find all root callers (methods with
no incoming CALLS edges). Returns paths from entry point to target."
```

---

### Task 8: Add `get_call_depth` to `traversal.py`

**Files:**
- Modify: `src/synapse/graph/traversal.py`
- Modify: `tests/unit/graph/test_traversal.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/graph/test_traversal.py`:

```python
from synapse.graph.traversal import get_call_depth


def test_get_call_depth_returns_callees() -> None:
    conn = _conn([
        ["Svc.DoA", "/proj/Svc.cs", 1],
        ["Repo.Save", "/proj/Repo.cs", 2],
    ])
    result = get_call_depth(conn, "Controller.Action", depth=3)
    assert result["root"] == "Controller.Action"
    assert len(result["callees"]) == 2
    assert result["callees"][0] == {"full_name": "Svc.DoA", "file_path": "/proj/Svc.cs", "depth": 1}
    assert result["depth_limit"] == 3


def test_get_call_depth_empty() -> None:
    conn = _conn([])
    result = get_call_depth(conn, "Leaf.Method", depth=2)
    assert result["callees"] == []
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/graph/test_traversal.py::test_get_call_depth_returns_callees -v
```

Expected: FAIL — `get_call_depth` not defined.

- [ ] **Step 3: Implement `get_call_depth`**

Add to `src/synapse/graph/traversal.py`:

```python
def get_call_depth(
    conn: GraphConnection,
    method: str,
    depth: int = 3,
) -> dict:
    """Recursive fanout — all methods reachable from a starting method up to N levels."""
    clamped = _clamp_depth(depth)
    rows = conn.query(
        f"MATCH p=(m:Method {{full_name: $method}})-[:CALLS*1..{clamped}]->(callee:Method) "
        "RETURN DISTINCT callee.full_name, callee.file_path, length(p) AS depth "
        "ORDER BY depth",
        {"method": method},
    )
    return {
        "root": method,
        "callees": [
            {"full_name": r[0], "file_path": r[1], "depth": r[2]}
            for r in rows
        ],
        "depth_limit": clamped,
    }
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/graph/test_traversal.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/synapse/graph/traversal.py tests/unit/graph/test_traversal.py
git commit -m "feat: add get_call_depth to graph/traversal.py

Returns all methods reachable from a starting method up to N hops,
annotated with their distance from the root."
```

---

### Task 9: Register multi-hop tools in MCP and service layer

**Files:**
- Modify: `src/synapse/service.py` (add 3 service methods)
- Modify: `src/synapse/mcp/tools.py` (register 3 tools)
- Modify: `src/synapse/cli/app.py` (add 3 CLI commands)

- [ ] **Step 1: Add service methods**

Add to `src/synapse/service.py`:

```python
    def trace_call_chain(self, start: str, end: str, max_depth: int = 6) -> dict:
        start = self._resolve(start)
        end = self._resolve(end)
        return trace_call_chain(self._conn, start, end, max_depth)

    def find_entry_points(self, method: str, max_depth: int = 8) -> dict:
        method = self._resolve(method)
        return find_entry_points(self._conn, method, max_depth)

    def get_call_depth(self, method: str, depth: int = 3) -> dict:
        method = self._resolve(method)
        return get_call_depth(self._conn, method, depth)
```

Add the import at the top:

```python
from synapse.graph.traversal import trace_call_chain, find_entry_points, get_call_depth
```

- [ ] **Step 2: Register MCP tools**

Add the following **inside the `register_tools(mcp, service)` function** in `src/synapse/mcp/tools.py` (all existing tools are defined inside this function — `mcp` and `service` are only in scope there):

```python
    @mcp.tool()
    def trace_call_chain(start: str, end: str, max_depth: int = 6) -> dict:
        """Find all call paths between two methods up to max_depth hops.

        Supports short names (e.g. 'CreateMeeting' instead of full namespace).
        Returns {paths: [[str]], start, end, max_depth}.
        """
        return service.trace_call_chain(start, end, max_depth)

    @mcp.tool()
    def find_entry_points(method: str, max_depth: int = 8) -> dict:
        """Find all root callers (no incoming CALLS edges) that eventually call a method.

        Useful for finding controller/API entry points that reach a given service method.
        Returns {entry_points: [{entry, path}], target, max_depth}.
        """
        return service.find_entry_points(method, max_depth)

    @mcp.tool()
    def get_call_depth(method: str, depth: int = 3) -> dict:
        """Get all methods reachable from a starting method up to N levels deep.

        Returns {root, callees: [{full_name, file_path, depth}], depth_limit}.
        """
        return service.get_call_depth(method, depth)
```

- [ ] **Step 3: Add CLI commands**

Add to `src/synapse/cli/app.py`:

```python
@app.command("trace")
def trace_chain(
    start: str = typer.Argument(help="Starting method"),
    end: str = typer.Argument(help="Ending method"),
    max_depth: int = typer.Option(6, "--depth", "-d"),
) -> None:
    """Trace call paths between two methods."""
    svc = _get_service()
    result = svc.trace_call_chain(start, end, max_depth)
    if not result["paths"]:
        typer.echo("No paths found.")
        return
    for i, path in enumerate(result["paths"], 1):
        typer.echo(f"Path {i}: {' → '.join(path)}")


@app.command("entry-points")
def entry_points(
    method: str = typer.Argument(help="Target method"),
    max_depth: int = typer.Option(8, "--depth", "-d"),
) -> None:
    """Find all entry points that eventually call a method."""
    svc = _get_service()
    result = svc.find_entry_points(method, max_depth)
    if not result["entry_points"]:
        typer.echo("No entry points found.")
        return
    for ep in result["entry_points"]:
        typer.echo(f"{ep['entry']} → {' → '.join(ep['path'][1:])}")


@app.command("call-depth")
def call_depth(
    method: str = typer.Argument(help="Starting method"),
    depth: int = typer.Option(3, "--depth", "-d"),
) -> None:
    """Show all methods reachable from a method up to N levels."""
    svc = _get_service()
    result = svc.get_call_depth(method, depth)
    if not result["callees"]:
        typer.echo("No callees found.")
        return
    for c in result["callees"]:
        indent = "  " * c["depth"]
        typer.echo(f"{indent}[depth {c['depth']}] {c['full_name']}")
```

- [ ] **Step 4: Run full unit suite**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/synapse/service.py src/synapse/mcp/tools.py src/synapse/cli/app.py
git commit -m "feat: register multi-hop call chain tools in MCP and CLI

Adds trace_call_chain, find_entry_points, get_call_depth as MCP tools
and CLI commands. All support short-name resolution."
```

---

## Chunk 4: Phase 3 — Impact Analysis Tools

### Task 10: Create `graph/analysis.py` with `analyze_change_impact`

**Files:**
- Create: `src/synapse/graph/analysis.py`
- Create: `tests/unit/graph/test_analysis.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/graph/test_analysis.py`:

```python
from unittest.mock import MagicMock

from synapse.graph.analysis import analyze_change_impact


def _conn(return_value: list) -> MagicMock:
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_analyze_change_impact_aggregates() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        [["Direct.Caller", "/proj/D.cs"]],  # direct callers
        [["Trans.Caller", "/proj/T.cs"]],  # transitive callers
        [["Test.Method", "/tests/T.cs"]],  # test coverage
    ]
    result = analyze_change_impact(conn, "Svc.Method")
    assert result["target"] == "Svc.Method"
    assert len(result["direct_callers"]) == 1
    assert len(result["transitive_callers"]) == 1
    assert len(result["test_coverage"]) == 1
    assert result["total_affected"] == 3


def test_analyze_change_impact_deduplicates_total() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        [["Shared.Caller", "/proj/S.cs"]],  # direct
        [["Shared.Caller", "/proj/S.cs"]],  # also in transitive
        [],  # no tests
    ]
    result = analyze_change_impact(conn, "Svc.Method")
    assert result["total_affected"] == 1  # deduplicated


def test_analyze_change_impact_empty() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], [], []]
    result = analyze_change_impact(conn, "Isolated.Method")
    assert result["direct_callers"] == []
    assert result["total_affected"] == 0
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/graph/test_analysis.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `analyze_change_impact`**

Create `src/synapse/graph/analysis.py`:

```python
"""Impact analysis and architectural audit queries.

These queries aggregate information across multiple graph traversals
to answer higher-level questions about change impact, interface contracts,
and architectural patterns.
"""

from synapse.graph.connection import GraphConnection
from synapse.graph.traversal import _clamp_depth


def analyze_change_impact(conn: GraphConnection, method: str) -> dict:
    """Structured impact report: direct callers, transitive callers, test coverage.

    Answers: 'If I change this method, what breaks?'
    """
    direct = conn.query(
        "MATCH (c:Method)-[:CALLS]->(m {full_name: $method}) "
        "RETURN c.full_name, c.file_path",
        {"method": method},
    )
    transitive = conn.query(
        "MATCH (c:Method)-[:CALLS*2..4]->(m {full_name: $method}) "
        "RETURN DISTINCT c.full_name, c.file_path",
        {"method": method},
    )
    tests = conn.query(
        "MATCH (t:Method)-[:CALLS*1..4]->(m {full_name: $method}) "
        "WHERE t.file_path CONTAINS 'Tests' "
        "RETURN DISTINCT t.full_name, t.file_path",
        {"method": method},
    )

    direct_callers = [{"full_name": r[0], "file_path": r[1]} for r in direct]
    transitive_callers = [{"full_name": r[0], "file_path": r[1]} for r in transitive]
    test_coverage = [{"full_name": r[0], "file_path": r[1]} for r in tests]

    all_names = {r["full_name"] for r in direct_callers + transitive_callers + test_coverage}

    return {
        "target": method,
        "direct_callers": direct_callers,
        "transitive_callers": transitive_callers,
        "test_coverage": test_coverage,
        "total_affected": len(all_names),
    }
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/graph/test_analysis.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/synapse/graph/analysis.py tests/unit/graph/test_analysis.py
git commit -m "feat: add analyze_change_impact to graph/analysis.py

Aggregates direct callers, transitive callers (2-4 hops), and test
coverage into a structured impact report with deduplicated total count."
```

---

### Task 11: Add `find_interface_contract` to `analysis.py`

**Files:**
- Modify: `src/synapse/graph/analysis.py`
- Modify: `tests/unit/graph/test_analysis.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/graph/test_analysis.py`:

```python
from synapse.graph.analysis import find_interface_contract


def test_find_interface_contract_returns_siblings() -> None:
    conn = _conn([
        ["Ns.IService", "Ns.IService.Do", "OtherImpl", "/proj/Other.cs"],
    ])
    result = find_interface_contract(conn, "Ns.MyImpl.Do")
    assert result["method"] == "Ns.MyImpl.Do"
    assert result["interface"] == "Ns.IService"
    assert result["contract_method"] == "Ns.IService.Do"
    assert len(result["sibling_implementations"]) == 1


def test_find_interface_contract_no_interface() -> None:
    conn = _conn([])
    result = find_interface_contract(conn, "Standalone.Method")
    assert result["sibling_implementations"] == []
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/graph/test_analysis.py::test_find_interface_contract_returns_siblings -v
```

Expected: FAIL — `find_interface_contract` not defined.

- [ ] **Step 3: Implement `find_interface_contract`**

Add to `src/synapse/graph/analysis.py`:

```python
def find_interface_contract(conn: GraphConnection, method: str) -> dict:
    """Find the interface a method satisfies and all sibling implementations.

    The method parameter should be a resolved full_name. The simple method
    name is extracted by splitting on '.' and taking the last segment.
    """
    simple_name = method.rsplit(".", 1)[-1]
    rows = conn.query(
        "MATCH (impl:Class)-[:CONTAINS]->(m:Method {name: $name}) "
        "WHERE m.full_name = $full_name "
        "MATCH (impl)-[:IMPLEMENTS]->(i)-[:CONTAINS]->(contract:Method {name: $name}) "
        "MATCH (sibling:Class)-[:IMPLEMENTS]->(i) "
        "WHERE sibling <> impl "
        "RETURN i.full_name, contract.full_name, sibling.name, sibling.file_path",
        {"name": simple_name, "full_name": method},
    )

    if not rows:
        return {
            "method": method,
            "interface": None,
            "contract_method": None,
            "sibling_implementations": [],
        }

    return {
        "method": method,
        "interface": rows[0][0],
        "contract_method": rows[0][1],
        "sibling_implementations": [
            {"class_name": r[2], "file_path": r[3]} for r in rows
        ],
    }
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/graph/test_analysis.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/synapse/graph/analysis.py tests/unit/graph/test_analysis.py
git commit -m "feat: add find_interface_contract to graph/analysis.py

Given an implementation method, finds the interface contract it satisfies
and all sibling implementations of that interface."
```

---

### Task 12: Add `find_type_impact` to `analysis.py`

**Files:**
- Modify: `src/synapse/graph/analysis.py`
- Modify: `tests/unit/graph/test_analysis.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/graph/test_analysis.py`:

```python
from synapse.graph.analysis import find_type_impact


def test_find_type_impact_categorizes() -> None:
    conn = _conn([
        ["Svc.Method", "/proj/Svc.cs", "prod"],
        ["Test.Verify", "/tests/Verify.cs", "test"],
    ])
    result = find_type_impact(conn, "Ns.MyModel")
    assert result["type"] == "Ns.MyModel"
    assert result["prod_count"] == 1
    assert result["test_count"] == 1
    assert len(result["references"]) == 2


def test_find_type_impact_empty() -> None:
    conn = _conn([])
    result = find_type_impact(conn, "Unused.Type")
    assert result["references"] == []
    assert result["prod_count"] == 0
    assert result["test_count"] == 0
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/graph/test_analysis.py::test_find_type_impact_categorizes -v
```

Expected: FAIL — `find_type_impact` not defined.

- [ ] **Step 3: Implement `find_type_impact`**

Add to `src/synapse/graph/analysis.py`:

```python
def find_type_impact(conn: GraphConnection, type_name: str) -> dict:
    """Find all symbols that reference a type, categorized as prod or test.

    Uses unlabeled (n) because REFERENCES edges can originate from any
    symbol type (Method, Class, Property, Field).
    """
    rows = conn.query(
        "MATCH (n)-[:REFERENCES]->(t {full_name: $type}) "
        "WHERE n.full_name IS NOT NULL "
        "RETURN n.full_name, n.file_path, "
        "CASE WHEN n.file_path CONTAINS 'Tests' THEN 'test' ELSE 'prod' END AS context",
        {"type": type_name},
    )

    references = [{"full_name": r[0], "file_path": r[1], "context": r[2]} for r in rows]
    prod_count = sum(1 for r in references if r["context"] == "prod")
    test_count = sum(1 for r in references if r["context"] == "test")

    return {
        "type": type_name,
        "references": references,
        "prod_count": prod_count,
        "test_count": test_count,
    }
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/graph/test_analysis.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/synapse/graph/analysis.py tests/unit/graph/test_analysis.py
git commit -m "feat: add find_type_impact to graph/analysis.py

Finds all symbols referencing a type, categorized as prod or test.
Uses unlabeled node match to catch all referencing symbol types."
```

---

### Task 13: Register impact analysis tools in MCP and service layer

**Files:**
- Modify: `src/synapse/service.py`
- Modify: `src/synapse/mcp/tools.py`
- Modify: `src/synapse/cli/app.py`

- [ ] **Step 1: Add service methods**

Add to `src/synapse/service.py`:

```python
    def analyze_change_impact(self, method: str) -> dict:
        method = self._resolve(method)
        return analyze_change_impact(self._conn, method)

    def find_interface_contract(self, method: str) -> dict:
        method = self._resolve(method)
        return find_interface_contract(self._conn, method)

    def find_type_impact(self, type_name: str) -> dict:
        type_name = self._resolve(type_name)
        return find_type_impact(self._conn, type_name)
```

Add the import:

```python
from synapse.graph.analysis import analyze_change_impact, find_interface_contract, find_type_impact
```

- [ ] **Step 2: Register MCP tools**

Add the following **inside the `register_tools(mcp, service)` function** in `src/synapse/mcp/tools.py`:

```python
    @mcp.tool()
    def analyze_change_impact(method: str) -> dict:
        """Analyze the impact of changing a method: direct callers, transitive callers, test coverage.

        Returns {target, direct_callers, transitive_callers, test_coverage, total_affected}.
        """
        return service.analyze_change_impact(method)

    @mcp.tool()
    def find_interface_contract(method: str) -> dict:
        """Find the interface contract a method satisfies and all sibling implementations.

        Returns {method, interface, contract_method, sibling_implementations}.
        """
        return service.find_interface_contract(method)

    @mcp.tool()
    def find_type_impact(type_name: str) -> dict:
        """Find all code affected if a type's shape changes, categorized as prod or test.

        Returns {type, references: [{full_name, file_path, context}], prod_count, test_count}.
        """
        return service.find_type_impact(type_name)
```

- [ ] **Step 3: Add CLI commands**

Add to `src/synapse/cli/app.py`:

```python
@app.command("impact")
def impact(
    method: str = typer.Argument(help="Method to analyze"),
) -> None:
    """Analyze the blast radius of changing a method."""
    svc = _get_service()
    result = svc.analyze_change_impact(method)
    typer.echo(f"Impact analysis for: {result['target']}")
    typer.echo(f"  Direct callers: {len(result['direct_callers'])}")
    typer.echo(f"  Transitive callers: {len(result['transitive_callers'])}")
    typer.echo(f"  Test coverage: {len(result['test_coverage'])}")
    typer.echo(f"  Total affected: {result['total_affected']}")
    for c in result["direct_callers"]:
        typer.echo(f"    [direct] {c['full_name']}")
    for c in result["transitive_callers"]:
        typer.echo(f"    [transitive] {c['full_name']}")
    for t in result["test_coverage"]:
        typer.echo(f"    [test] {t['full_name']}")


@app.command("contract")
def contract(
    method: str = typer.Argument(help="Implementation method"),
) -> None:
    """Find the interface contract and sibling implementations for a method."""
    svc = _get_service()
    result = svc.find_interface_contract(method)
    if not result["interface"]:
        typer.echo("No interface contract found.")
        return
    typer.echo(f"Interface: {result['interface']}")
    typer.echo(f"Contract: {result['contract_method']}")
    for s in result["sibling_implementations"]:
        typer.echo(f"  Sibling: {s['class_name']} ({s['file_path']})")


@app.command("type-impact")
def type_impact(
    type_name: str = typer.Argument(help="Type to analyze"),
) -> None:
    """Find all code affected if a type changes shape."""
    svc = _get_service()
    result = svc.find_type_impact(type_name)
    typer.echo(f"Type impact for: {result['type']}")
    typer.echo(f"  Prod references: {result['prod_count']}")
    typer.echo(f"  Test references: {result['test_count']}")
    for r in result["references"]:
        typer.echo(f"    [{r['context']}] {r['full_name']}")
```

- [ ] **Step 4: Run full unit suite**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/synapse/service.py src/synapse/mcp/tools.py src/synapse/cli/app.py
git commit -m "feat: register impact analysis tools in MCP and CLI

Adds analyze_change_impact, find_interface_contract, find_type_impact
as MCP tools and CLI commands. All support short-name resolution."
```

---

## Chunk 5: Phase 4 & 5 — Architectural Audit and Summary Generation

### Task 14: Add `audit_architecture` to `analysis.py`

**Files:**
- Modify: `src/synapse/graph/analysis.py`
- Modify: `tests/unit/graph/test_analysis.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/graph/test_analysis.py`:

```python
from synapse.graph.analysis import audit_architecture


def test_audit_layering_violations() -> None:
    conn = _conn([["UsersController", "GetAll", "AppDbContext.Users"]])
    result = audit_architecture(conn, "layering_violations")
    assert result["rule"] == "layering_violations"
    assert result["count"] == 1
    assert len(result["violations"]) == 1


def test_audit_untested_services() -> None:
    conn = _conn([["UserService", "/proj/Services/UserService.cs"]])
    result = audit_architecture(conn, "untested_services")
    assert result["rule"] == "untested_services"
    assert result["count"] == 1


def test_audit_repeated_db_writes() -> None:
    conn = _conn([["Svc.CreateAsync", 2]])
    result = audit_architecture(conn, "repeated_db_writes")
    assert result["rule"] == "repeated_db_writes"
    assert result["count"] == 1


def test_audit_invalid_rule_raises() -> None:
    import pytest
    conn = _conn([])
    with pytest.raises(ValueError, match="Unknown rule"):
        audit_architecture(conn, "nonexistent_rule")


def test_audit_empty_results() -> None:
    conn = _conn([])
    result = audit_architecture(conn, "layering_violations")
    assert result["count"] == 0
    assert result["violations"] == []
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/graph/test_analysis.py::test_audit_layering_violations -v
```

Expected: FAIL — `audit_architecture` not defined.

- [ ] **Step 3: Implement `audit_architecture`**

Add to `src/synapse/graph/analysis.py`:

```python
# These audit rules are C#/.NET-specific. If Synapse later supports other
# languages, these rules need language-aware variants or should be skipped
# for non-C# projects.

_AUDIT_RULES: dict[str, tuple[str, str]] = {
    "layering_violations": (
        "Controllers that bypass the service layer and call DbContext directly",
        "MATCH (ctrl:Class)-[:CONTAINS]->(m:Method)-[:CALLS]->(db:Method) "
        "WHERE ctrl.file_path CONTAINS 'Controllers' "
        "AND db.full_name CONTAINS 'DbContext' "
        "RETURN ctrl.name, m.name, db.full_name",
    ),
    "untested_services": (
        "Service classes with no test methods calling into them",
        "MATCH (svc:Class)-[:IMPLEMENTS]->(i) "
        "WHERE svc.file_path CONTAINS '/Services/' "
        "OPTIONAL MATCH (t:Method)-[:CALLS*1..3]->(:Method)<-[:CONTAINS]-(svc) "
        "WHERE t.file_path CONTAINS 'Tests' "
        "WITH svc, t "
        "WHERE t IS NULL "
        "RETURN DISTINCT svc.name, svc.file_path",
    ),
    "repeated_db_writes": (
        "Methods calling multiple distinct SaveChangesAsync targets. "
        "NOTE: CALLS edges are created with MERGE, so this counts distinct "
        "callees, not call sites. It detects methods calling SaveChangesAsync "
        "on multiple DbContext types but not repeated calls to the same one.",
        "MATCH (m:Method)-[:CALLS]->(save:Method) "
        "WHERE save.name = 'SaveChangesAsync' "
        "WITH m, count(save) AS save_count "
        "WHERE save_count > 1 "
        "RETURN m.full_name, save_count ORDER BY save_count DESC",
    ),
}


def audit_architecture(conn: GraphConnection, rule: str) -> dict:
    """Run an architectural audit rule against the graph.

    Valid rules: layering_violations, untested_services, repeated_db_writes.
    """
    if rule not in _AUDIT_RULES:
        valid = ", ".join(sorted(_AUDIT_RULES.keys()))
        raise ValueError(f"Unknown rule '{rule}'. Valid rules: {valid}")

    description, cypher = _AUDIT_RULES[rule]
    rows = conn.query(cypher)

    violations = [dict(zip(range(len(r)), r)) for r in rows]

    return {
        "rule": rule,
        "description": description,
        "violations": violations,
        "count": len(violations),
    }
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/graph/test_analysis.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/synapse/graph/analysis.py tests/unit/graph/test_analysis.py
git commit -m "feat: add audit_architecture to graph/analysis.py

Dispatches C#/.NET-specific architectural rules: layering_violations,
untested_services, repeated_db_writes. Rules are data-driven via
_AUDIT_RULES dict for easy extension."
```

---

### Task 15: Add `summarize_from_graph` to service layer

**Files:**
- Modify: `src/synapse/service.py`
- Create: `tests/unit/test_summarize.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_summarize.py`:

```python
from unittest.mock import MagicMock, patch

from synapse.service import SynapseService


def test_summarize_from_graph_formats_output() -> None:
    conn = MagicMock()
    service = SynapseService(conn)

    with patch("synapse.service.resolve_full_name", return_value="Ns.MyService"):
        with patch("synapse.service.get_symbol") as mock_sym:
            mock_sym.return_value = {
                "full_name": "Ns.MyService",
                "name": "MyService",
                "kind": "class",
                "file_path": "/proj/MyService.cs",
            }
            with patch("synapse.service.get_implemented_interfaces") as mock_ifaces:
                mock_ifaces.return_value = [{"full_name": "Ns.IMyService"}]
                with patch("synapse.service.get_members_overview") as mock_members:
                    mock_members.return_value = [
                        {"name": "DoA"}, {"name": "DoB"}, {"name": "DoC"},
                    ]
                    with patch.object(service, "find_dependencies", return_value=[
                        {"type": {"full_name": "Ns.DbContext"}},
                    ]):
                        with patch.object(service, "find_type_impact", return_value={
                            "references": [
                                {"full_name": "Ns.Controller.Action", "context": "prod"},
                            ],
                            "prod_count": 1,
                            "test_count": 0,
                        }):
                            result = service.summarize_from_graph("MyService")

    assert result["full_name"] == "Ns.MyService"
    assert "MyService" in result["summary"]
    assert "IMyService" in result["summary"]
    assert result["data"]["method_count"] == 3
    assert "Ns.DbContext" in result["data"]["dependencies"]


def test_summarize_from_graph_unknown_symbol() -> None:
    conn = MagicMock()
    service = SynapseService(conn)

    with patch("synapse.service.resolve_full_name", return_value="Unknown"):
        with patch("synapse.service.get_symbol", return_value=None):
            result = service.summarize_from_graph("Unknown")

    assert result is None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/test_summarize.py -v
```

Expected: FAIL — `summarize_from_graph` method doesn't exist.

- [ ] **Step 3: Implement `summarize_from_graph`**

Add to `src/synapse/service.py`:

```python
    def summarize_from_graph(self, class_name: str) -> dict | None:
        """Auto-generate a structural summary of a class from graph data.

        The summary is returned but NOT stored automatically. Call set_summary
        to persist it after review.
        """
        class_name = self._resolve(class_name)
        symbol = _p(get_symbol(self._conn, class_name))
        if not symbol:
            return None

        interfaces = [
            _p(i)["full_name"]
            for i in get_implemented_interfaces(self._conn, class_name)
        ]

        members = get_members_overview(self._conn, class_name)
        method_count = len(members)

        deps = self.find_dependencies(class_name)
        dep_names = list({d["type"]["full_name"] for d in deps})

        impact = self.find_type_impact(class_name)
        dependents = [r["full_name"] for r in impact["references"] if r["context"] == "prod"]
        # Extract class names from test method full_names (e.g. "Tests.FooTest.TestMethod" → "Tests.FooTest")
        # and deduplicate, since multiple test methods in the same class should count once
        test_classes = list({
            r["full_name"].rsplit(".", 1)[0]
            for r in impact["references"]
            if r["context"] == "test"
        })

        # Build summary text
        parts = []
        name = symbol.get("name", class_name)
        if interfaces:
            parts.append(f"{name}: implements {', '.join(i.rsplit('.', 1)[-1] for i in interfaces)} ({method_count} methods).")
        else:
            parts.append(f"{name}: {symbol.get('kind', 'class')} ({method_count} methods).")

        if dep_names:
            parts.append(f"Dependencies: {', '.join(n.rsplit('.', 1)[-1] for n in dep_names)}.")

        if dependents or test_classes:
            dep_str = f"{len(dependents)} prod references" if dependents else ""
            test_str = f"{len(test_classes)} test references" if test_classes else ""
            combined = ", ".join(filter(None, [dep_str, test_str]))
            parts.append(f"Depended on by: {combined}.")

        return {
            "full_name": class_name,
            "summary": "\n".join(parts),
            "data": {
                "kind": symbol.get("kind", "class"),
                "interfaces": interfaces,
                "method_count": method_count,
                "dependencies": dep_names,
                "dependents": dependents,
                "test_classes": test_classes,
            },
        }
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/test_summarize.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/synapse/service.py tests/unit/test_summarize.py
git commit -m "feat: add summarize_from_graph to service layer

Auto-generates structural summary from graph data: interfaces, method
count, dependencies, dependents, test coverage. Summary is returned
but not stored — call set_summary to persist after review."
```

---

### Task 16: Register audit and summary tools in MCP and CLI

**Files:**
- Modify: `src/synapse/service.py` (add `audit_architecture` service method)
- Modify: `src/synapse/mcp/tools.py`
- Modify: `src/synapse/cli/app.py`

- [ ] **Step 1: Add service method for `audit_architecture`**

Add to `src/synapse/service.py`:

```python
    def audit_architecture(self, rule: str) -> dict:
        return audit_architecture(self._conn, rule)
```

Add the import:

```python
from synapse.graph.analysis import audit_architecture
```

(Note: `analyze_change_impact`, `find_interface_contract`, `find_type_impact` imports were added in Task 13.)

- [ ] **Step 2: Register MCP tools**

Add the following **inside the `register_tools(mcp, service)` function** in `src/synapse/mcp/tools.py`:

```python
    @mcp.tool()
    def audit_architecture(rule: str) -> dict:
        """Run an architectural audit rule against the codebase graph.

        Valid rules: layering_violations, untested_services, repeated_db_writes.
        Returns {rule, description, violations: [dict], count}.
        These rules are C#/.NET-specific.
        """
        return service.audit_architecture(rule)

    @mcp.tool()
    def summarize_from_graph(class_name: str) -> dict:
        """Auto-generate a structural summary of a class from graph data.

        Returns {full_name, summary, data: {kind, interfaces, method_count, dependencies, dependents, test_classes}}.
        The summary is NOT stored automatically — call set_summary to persist after review.
        """
        return service.summarize_from_graph(class_name)
```

- [ ] **Step 3: Add CLI commands**

Add to `src/synapse/cli/app.py`:

```python
@app.command("audit")
def audit(
    rule: str = typer.Argument(help="Rule: layering_violations, untested_services, repeated_db_writes"),
) -> None:
    """Run an architectural audit rule."""
    svc = _get_service()
    try:
        result = svc.audit_architecture(rule)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    typer.echo(f"Rule: {result['rule']} — {result['description']}")
    typer.echo(f"Violations: {result['count']}")
    for v in result["violations"]:
        typer.echo(f"  {v}")


@app.command("summarize")
def summarize(
    class_name: str = typer.Argument(help="Class to summarize"),
) -> None:
    """Auto-generate a structural summary of a class from graph data."""
    svc = _get_service()
    result = svc.summarize_from_graph(class_name)
    if not result:
        typer.echo("Symbol not found.")
        raise typer.Exit(1)
    typer.echo(result["summary"])
    typer.echo(f"\nTo persist: synapse summary set '{result['full_name']}' '<content>'")
```

- [ ] **Step 4: Run full unit suite**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/synapse/service.py src/synapse/mcp/tools.py src/synapse/cli/app.py
git commit -m "feat: register audit_architecture and summarize_from_graph in MCP and CLI

Completes the tool registration for all roadmap features. Total tool
count: 29 (21 existing + 8 new)."
```

---

### Task 17: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full unit suite**

```bash
cd /Users/alex/Dev/mcpcontext && source .venv/bin/activate
pytest tests/unit/ -v --tb=short
```

Expected: All tests pass (153 existing + ~25 new).

- [ ] **Step 2: Verify tool count**

```bash
grep -c '@mcp.tool' src/synapse/mcp/tools.py
```

Expected: 29

- [ ] **Step 3: Verify no broken imports**

```bash
python -c "from synapse.graph.lookups import resolve_full_name, check_staleness; print('lookups OK')"
python -c "from synapse.graph.traversal import trace_call_chain, find_entry_points, get_call_depth; print('traversal OK')"
python -c "from synapse.graph.analysis import analyze_change_impact, find_interface_contract, find_type_impact, audit_architecture; print('analysis OK')"
python -c "from synapse.service import SynapseService; print('service OK')"
```

Expected: All print OK.

- [ ] **Step 4: If FalkorDB + .NET available, run integration tests**

```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb:latest &
sleep 3
pytest tests/mcp/ -v -m integration
pytest tests/integration/ -v -m integration
```

Key checks:
- Multi-hop tools return results on the test fixture
- Impact analysis works for `Dog.Speak` → should find `AnimalService` as caller
- `summarize_from_graph("Animal")` should produce meaningful output
