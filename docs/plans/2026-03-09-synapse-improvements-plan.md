# Synapse Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 3 bugs, add 3 behavior improvements, add 5 doc improvements, and 2 nice-to-have features across queries.py, service.py, and tools.py.

**Architecture:** Each change touches at most three layers in lockstep: `queries.py` (Cypher), `service.py` (thin delegation), `tools.py` (MCP tool descriptions/params). Tests live in `tests/unit/test_queries.py` (new file) and `tests/unit/test_tools.py` (new file), following the mock pattern in `tests/unit/test_service.py`.

**Tech Stack:** Python 3.11+, FalkorDB (`falkordb.node.Node`), FastMCP, `unittest.mock`

---

## Task 1: Fix `list_summarized` duplicates

**Files:**
- Modify: `src/synapse/graph/queries.py:83-91`
- Create: `tests/unit/test_queries.py`

**Step 1: Write the failing test**

Create `tests/unit/test_queries.py`:

```python
from unittest.mock import MagicMock
from falkordb.node import Node as FalkorNode
from synapse.graph.queries import list_summarized


def _node(labels, props):
    return FalkorNode(node_id=1, labels=labels, properties=props)


def _conn(return_value):
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_list_summarized_deduplicates():
    node = _node(["Class", "Summarized"], {"full_name": "A.B"})
    # Simulate the same node returned twice (two traversal paths)
    conn = _conn([[node], [node]])
    result = list_summarized(conn)
    assert len(result) == 1
```

**Step 2: Run to confirm it fails**

```bash
cd /Users/alex/Dev/mcpcontext && source .venv/bin/activate
pytest tests/unit/test_queries.py::test_list_summarized_deduplicates -v
```
Expected: FAIL (returns 2 items, not 1)

**Step 3: Fix `list_summarized` in `queries.py`**

Replace both query strings to add `WITH DISTINCT n`:

```python
def list_summarized(conn: GraphConnection, project_path: str | None = None) -> list[dict]:
    if project_path:
        rows = conn.query(
            "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n:Summarized) "
            "WITH DISTINCT n RETURN n",
            {"path": project_path},
        )
    else:
        rows = conn.query("MATCH (n:Summarized) WITH DISTINCT n RETURN n")
    return [r[0] for r in rows]
```

**Step 4: Run test to confirm it passes**

```bash
pytest tests/unit/test_queries.py::test_list_summarized_deduplicates -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_queries.py src/synapse/graph/queries.py
git commit -m "fix: deduplicate list_summarized results with DISTINCT"
```

---

## Task 2: Fix `search_symbols` kind error message + add Interface

**Files:**
- Modify: `src/synapse/graph/queries.py:7-10,60-61`
- Modify: `tests/unit/test_queries.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_queries.py`:

```python
import pytest
from synapse.graph.queries import search_symbols, _VALID_KINDS


def test_search_symbols_invalid_kind_lists_valid_values():
    conn = _conn([])
    with pytest.raises(ValueError, match="Valid values"):
        search_symbols(conn, "Foo", kind="widget")


def test_search_symbols_interface_kind_is_valid():
    conn = _conn([])
    # Should not raise
    search_symbols(conn, "IRepo", kind="Interface")


def test_valid_kinds_contains_interface():
    assert "Interface" in _VALID_KINDS
```

**Step 2: Run to confirm they fail**

```bash
pytest tests/unit/test_queries.py::test_search_symbols_invalid_kind_lists_valid_values \
       tests/unit/test_queries.py::test_search_symbols_interface_kind_is_valid \
       tests/unit/test_queries.py::test_valid_kinds_contains_interface -v
```
Expected: all FAIL

**Step 3: Fix `_VALID_KINDS` and error message in `queries.py`**

```python
_VALID_KINDS = frozenset({
    "Class", "Interface", "Method", "Property", "Field", "Namespace",
    "File", "Directory", "Repository",
})
```

```python
def search_symbols(conn: GraphConnection, query: str, kind: str | None = None) -> list[dict]:
    if kind and kind not in _VALID_KINDS:
        raise ValueError(
            f"Unknown symbol kind: {kind!r}. Valid values: {sorted(_VALID_KINDS)}"
        )
    ...
```

**Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/test_queries.py::test_search_symbols_invalid_kind_lists_valid_values \
       tests/unit/test_queries.py::test_search_symbols_interface_kind_is_valid \
       tests/unit/test_queries.py::test_valid_kinds_contains_interface -v
```
Expected: all PASS

**Step 5: Commit**

```bash
git add src/synapse/graph/queries.py tests/unit/test_queries.py
git commit -m "fix: add Interface to valid kinds; include valid values in kind error message"
```

---

## Task 3: Fix `get_symbol_source` stale error message

**Files:**
- Modify: `src/synapse/mcp/tools.py:32-34`
- Create: `tests/unit/test_tools.py`

The fix goes in `tools.py`, not `service.py`, because `service.get_symbol_source` already returns `None` when source is unavailable — the tool layer just needs to distinguish "node missing" from "node exists but no source".

**Step 1: Write the failing test**

Create `tests/unit/test_tools.py`:

```python
from unittest.mock import MagicMock, patch


def _make_mcp_and_service():
    mcp = MagicMock()
    mcp.tool.return_value = lambda f: f  # decorator passthrough
    service = MagicMock()
    return mcp, service


def _register(mcp, service):
    from synapse.mcp.tools import register_tools
    register_tools(mcp, service)


def test_get_symbol_source_node_missing():
    mcp, service = _make_mcp_and_service()
    service.get_symbol_source.return_value = None
    service.get_symbol.return_value = None  # node does not exist
    _register(mcp, service)

    tool_fn = mcp.tool.call_args_list
    # tools.py registers functions as decorated; we need to call the actual function
    # Instead, test via the registered function directly
    from synapse.mcp import tools as tools_module
    import synapse.mcp.tools as t

    # Re-register capturing the actual functions
    registered = {}
    real_mcp = MagicMock()
    real_mcp.tool.return_value = lambda f: registered.__setitem__(f.__name__, f) or f
    service2 = MagicMock()
    service2.get_symbol_source.return_value = None
    service2.get_symbol.return_value = None
    from synapse.mcp.tools import register_tools
    register_tools(real_mcp, service2)

    result = registered["get_symbol_source"]("Ns.Missing")
    assert result == "Symbol not found: Ns.Missing"


def test_get_symbol_source_stale_index():
    registered = {}
    real_mcp = MagicMock()
    real_mcp.tool.return_value = lambda f: registered.__setitem__(f.__name__, f) or f
    service = MagicMock()
    service.get_symbol_source.return_value = None
    service.get_symbol.return_value = {"full_name": "Ns.Cls"}  # node exists

    from synapse.mcp.tools import register_tools
    register_tools(real_mcp, service)

    result = registered["get_symbol_source"]("Ns.Cls")
    assert "re-index" in result.lower()
    assert "Symbol not found" not in result
```

**Step 2: Run to confirm they fail**

```bash
pytest tests/unit/test_tools.py -v
```
Expected: FAIL (`test_get_symbol_source_stale_index` fails — returns "Symbol not found" instead of re-index message)

**Step 3: Fix `get_symbol_source` in `tools.py`**

```python
@mcp.tool()
def get_symbol_source(full_name: str, include_class_signature: bool = False) -> str:
    result = service.get_symbol_source(full_name, include_class_signature)
    if result is not None:
        return result
    if service.get_symbol(full_name) is not None:
        return f"Source not available for {full_name} — re-index required"
    return f"Symbol not found: {full_name}"
```

**Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/test_tools.py -v
```
Expected: all PASS

**Step 5: Commit**

```bash
git add src/synapse/mcp/tools.py tests/unit/test_tools.py
git commit -m "fix: distinguish stale-index from missing symbol in get_symbol_source"
```

---

## Task 4: `find_callers` interface dispatch

**Files:**
- Modify: `src/synapse/graph/queries.py:31-36`
- Modify: `src/synapse/service.py:93-94`
- Modify: `src/synapse/mcp/tools.py:41-43`
- Modify: `tests/unit/test_queries.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_queries.py`:

```python
from synapse.graph.queries import find_callers


def test_find_callers_includes_interface_dispatch_by_default():
    direct_caller = _node(["Method"], {"full_name": "A.Direct"})
    iface_caller = _node(["Method"], {"full_name": "A.ViaInterface"})
    conn = MagicMock()
    # First query (direct), second query (interface dispatch)
    conn.query.side_effect = [[[ direct_caller]], [[iface_caller]]]

    result = find_callers(conn, "Svc.DoWork")
    assert len(result) == 2


def test_find_callers_direct_only_when_disabled():
    direct_caller = _node(["Method"], {"full_name": "A.Direct"})
    conn = _conn([[direct_caller]])

    result = find_callers(conn, "Svc.DoWork", include_interface_dispatch=False)
    assert len(result) == 1
    conn.query.assert_called_once()
```

**Step 2: Run to confirm they fail**

```bash
pytest tests/unit/test_queries.py::test_find_callers_includes_interface_dispatch_by_default \
       tests/unit/test_queries.py::test_find_callers_direct_only_when_disabled -v
```
Expected: FAIL (no `include_interface_dispatch` param)

**Step 3: Update `find_callers` in `queries.py`**

```python
def find_callers(
    conn: GraphConnection,
    method_full_name: str,
    include_interface_dispatch: bool = True,
) -> list[dict]:
    direct = conn.query(
        "MATCH (caller:Method)-[:CALLS]->(m:Method {full_name: $full_name}) RETURN caller",
        {"full_name": method_full_name},
    )
    if not include_interface_dispatch:
        return [r[0] for r in direct]
    via_iface = conn.query(
        "MATCH (caller:Method)-[:CALLS]->(im:Method)"
        "<-[:IMPLEMENTS]-(m:Method {full_name: $full_name}) RETURN caller",
        {"full_name": method_full_name},
    )
    seen = set()
    result = []
    for row in direct + via_iface:
        node = row[0]
        key = node.properties.get("full_name") if hasattr(node, "properties") else node.get("full_name")
        if key not in seen:
            seen.add(key)
            result.append(node)
    return result
```

**Step 4: Update `SynapseService.find_callers` in `service.py`**

```python
def find_callers(self, method_full_name: str, include_interface_dispatch: bool = True) -> list[dict]:
    return [_p(item) for item in find_callers(self._conn, method_full_name, include_interface_dispatch)]
```

**Step 5: Update MCP tool in `tools.py`**

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

**Step 6: Run tests**

```bash
pytest tests/unit/test_queries.py -v
```
Expected: all PASS

**Step 7: Commit**

```bash
git add src/synapse/graph/queries.py src/synapse/service.py src/synapse/mcp/tools.py tests/unit/test_queries.py
git commit -m "feat: find_callers traverses interface dispatch by default"
```

---

## Task 5: `find_implementations` short name fallback

**Files:**
- Modify: `src/synapse/graph/queries.py:21-28`
- Modify: `tests/unit/test_queries.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_queries.py`:

```python
from synapse.graph.queries import find_implementations


def test_find_implementations_falls_back_to_short_name():
    impl = _node(["Class"], {"full_name": "MyNs.MyClass"})
    conn = MagicMock()
    # First call (exact match) returns empty; second call (suffix fallback) returns result
    conn.query.side_effect = [[], [impl]]

    result = find_implementations(conn, "IMyInterface")
    assert len(result) == 1
    assert conn.query.call_count == 2


def test_find_implementations_exact_match_does_not_fallback():
    impl = _node(["Class"], {"full_name": "MyNs.MyClass"})
    conn = _conn([[impl]])

    result = find_implementations(conn, "MyNs.IMyInterface")
    assert len(result) == 1
    assert conn.query.call_count == 1  # no fallback needed
```

**Step 2: Run to confirm they fail**

```bash
pytest tests/unit/test_queries.py::test_find_implementations_falls_back_to_short_name \
       tests/unit/test_queries.py::test_find_implementations_exact_match_does_not_fallback -v
```
Expected: FAIL

**Step 3: Update `find_implementations` in `queries.py`**

```python
def find_implementations(conn: GraphConnection, interface_full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (c:Class)-[:IMPLEMENTS]->(i {full_name: $full_name}) RETURN c "
        "UNION "
        "MATCH (c:Class)-[:INHERITS*]->(base:Class)-[:IMPLEMENTS]->(i {full_name: $full_name}) RETURN c",
        {"full_name": interface_full_name},
    )
    if rows:
        return [r[0] for r in rows]
    # Fallback: suffix match for short names (e.g. "IFoo" matches "MyNs.IFoo")
    rows = conn.query(
        "MATCH (c:Class)-[:IMPLEMENTS]->(i:Interface) "
        "WHERE i.full_name ENDS WITH ('.' + $name) OR i.full_name = $name "
        "RETURN c "
        "UNION "
        "MATCH (c:Class)-[:INHERITS*]->(base:Class)-[:IMPLEMENTS]->(i:Interface) "
        "WHERE i.full_name ENDS WITH ('.' + $name) OR i.full_name = $name "
        "RETURN c",
        {"name": interface_full_name},
    )
    return [r[0] for r in rows]
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_queries.py -v
```
Expected: all PASS

**Step 5: Update MCP tool description in `tools.py`**

```python
@mcp.tool()
def find_implementations(interface_name: str) -> list[dict]:
    """Find all classes that implement the given interface.

    Accepts both full names (e.g. "MyNs.IFoo") and short names (e.g. "IFoo").
    Short names use a suffix match when an exact match is not found.
    """
    return service.find_implementations(interface_name)
```

**Step 6: Run full unit suite**

```bash
pytest tests/unit/ -v
```
Expected: all PASS

**Step 7: Commit**

```bash
git add src/synapse/graph/queries.py src/synapse/mcp/tools.py tests/unit/test_queries.py
git commit -m "feat: find_implementations accepts short names via suffix fallback"
```

---

## Task 6: `get_hierarchy` includes interface implementations

**Files:**
- Modify: `src/synapse/graph/queries.py:47-56`
- Modify: `tests/unit/test_queries.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_queries.py`:

```python
from synapse.graph.queries import get_hierarchy


def test_get_hierarchy_includes_implements():
    iface = _node(["Interface"], {"full_name": "MyNs.IFoo"})
    conn = MagicMock()
    # Three queries: parents, children, implements
    conn.query.side_effect = [[], [], [[iface]]]

    result = get_hierarchy(conn, "MyNs.Foo")
    assert "implements" in result
    assert len(result["implements"]) == 1


def test_get_hierarchy_implements_empty_when_none():
    conn = MagicMock()
    conn.query.side_effect = [[], [], []]

    result = get_hierarchy(conn, "MyNs.Foo")
    assert result["implements"] == []
```

**Step 2: Run to confirm they fail**

```bash
pytest tests/unit/test_queries.py::test_get_hierarchy_includes_implements \
       tests/unit/test_queries.py::test_get_hierarchy_implements_empty_when_none -v
```
Expected: FAIL (no `implements` key)

**Step 3: Update `get_hierarchy` in `queries.py`**

```python
def get_hierarchy(conn: GraphConnection, class_full_name: str) -> dict:
    parents = conn.query(
        "MATCH (c:Class {full_name: $full_name})-[:INHERITS*]->(p:Class) RETURN p",
        {"full_name": class_full_name},
    )
    children = conn.query(
        "MATCH (c:Class)-[:INHERITS*]->(p:Class {full_name: $full_name}) RETURN c",
        {"full_name": class_full_name},
    )
    implements = conn.query(
        "MATCH (c:Class {full_name: $full_name})-[:IMPLEMENTS]->(i:Interface) RETURN i",
        {"full_name": class_full_name},
    )
    return {
        "parents": [r[0] for r in parents],
        "children": [r[0] for r in children],
        "implements": [r[0] for r in implements],
    }
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_queries.py -v
```
Expected: all PASS

**Step 5: Update MCP tool description in `tools.py`**

```python
@mcp.tool()
def get_hierarchy(class_name: str) -> dict:
    """Return the inheritance hierarchy for a class.

    Returns {"parents": [...], "children": [...], "implements": [...]}.
    "implements" lists interfaces directly implemented by this class.
    """
    return service.get_hierarchy(class_name)
```

**Step 6: Run full unit suite**

```bash
pytest tests/unit/ -v
```
Expected: all PASS

**Step 7: Commit**

```bash
git add src/synapse/graph/queries.py src/synapse/mcp/tools.py tests/unit/test_queries.py
git commit -m "feat: get_hierarchy includes implements field for interface relationships"
```

---

## Task 7: Documentation — `get_schema` tool + `execute_query` inline schema

**Files:**
- Modify: `src/synapse/mcp/tools.py`

No query changes. No tests needed (static data, no logic).

**Step 1: Add `get_schema` tool and update `execute_query` description**

In `tools.py`, add before `execute_query`:

```python
_GRAPH_SCHEMA = {
    "node_labels": {
        "Repository": ["path", "name", "last_indexed"],
        "Directory": ["path", "name"],
        "File": ["path", "name"],
        "Package": ["name"],
        "Class": ["full_name", "name", "kind", "file_path", "line", "end_line", "signature"],
        "Interface": ["full_name", "name", "file_path", "line", "end_line"],
        "Method": ["full_name", "name", "file_path", "line", "end_line", "signature"],
        "Property": ["full_name", "name", "file_path", "line"],
        "Field": ["full_name", "name", "file_path", "line"],
    },
    "relationship_types": {
        "CONTAINS": "Repository/Directory/File/Class/Interface → any",
        "INHERITS": "Class → Class",
        "IMPLEMENTS": "Class → Interface  |  Method → Method (concrete implements interface method)",
        "CALLS": "Method → Method",
        "REFERENCES": "any → Class/Interface (field type, param type, return type)",
    },
    "notes": [
        "execute_query accepts read-only Cypher only (no CREATE/MERGE/SET/DELETE/REMOVE/DROP).",
        "Nodes with summaries also carry the :Summarized label and a 'summary' property.",
        "Class.kind values: 'class', 'abstract_class', 'enum', 'record'.",
    ],
}
```

Add `get_schema` tool:

```python
@mcp.tool()
def get_schema() -> dict:
    """Return the full graph schema: node labels with properties, relationship types, and usage notes.

    Use this before writing raw Cypher for execute_query.
    """
    return _GRAPH_SCHEMA
```

Update `execute_query` docstring:

```python
@mcp.tool()
def execute_query(cypher: str) -> list[dict]:
    """Execute a read-only Cypher query against the graph.

    Read-only: CREATE, MERGE, SET, DELETE, REMOVE, DROP are blocked.

    Schema summary (call get_schema() for full details):
      Nodes: Repository, Directory, File, Package, Class, Interface, Method, Property, Field
      Edges: CONTAINS, INHERITS, IMPLEMENTS, CALLS, REFERENCES
      Key properties: full_name, name, file_path, line, end_line, signature, kind

    Example: MATCH (m:Method {full_name: 'MyNs.MyClass.MyMethod'}) RETURN m
    """
    return service.execute_query(cypher)
```

**Step 2: Run full unit suite to check no regressions**

```bash
pytest tests/unit/ -v
```
Expected: all PASS

**Step 3: Commit**

```bash
git add src/synapse/mcp/tools.py
git commit -m "docs: add get_schema tool and inline schema summary in execute_query"
```

---

## Task 8: Documentation — remaining tool descriptions (#8–11)

**Files:**
- Modify: `src/synapse/mcp/tools.py`

No logic changes. Update docstrings only.

**Step 1: Update `search_symbols`**

```python
@mcp.tool()
def search_symbols(
    query: str,
    kind: str | None = None,
    namespace: str | None = None,
    file_path: str | None = None,
) -> list[dict]:
    """Search for symbols by name substring.

    kind: filter by node type. Valid values: Class, Interface, Method, Property,
          Field, Namespace, File, Directory, Repository.
    namespace: filter to symbols whose full_name starts with this prefix
               (e.g. "MyNs.Services").
    file_path: filter to symbols defined in this file path.
    """
    return service.search_symbols(query, kind, namespace, file_path)
```

(The namespace/file_path params are added here in advance of Task 9 — this step adds them to the tool signature with forwarding; queries.py support comes in Task 9.)

**Step 2: Update `find_callees`**

```python
@mcp.tool()
def find_callees(method_full_name: str) -> list[dict]:
    """Find methods called by the given method (direct CALLS edges only).

    Note: in C# DI codebases, callees are often interface methods. The graph
    stores the edge to the concrete or interface method depending on the call site.
    """
    return service.find_callees(method_full_name)
```

**Step 3: Update `get_context_for`**

```python
@mcp.tool()
def get_context_for(full_name: str) -> str:
    """Return a rich markdown summary of a symbol and its direct dependencies.

    The returned markdown includes:
    - The symbol's source code (if available; otherwise a re-index note)
    - Each direct field-type dependency with its full member signature list
    - Summaries for any summarized dependencies

    Useful for giving an AI full context before asking it to modify a class.
    """
    result = service.get_context_for(full_name)
    return result or f"Symbol not found: {full_name}"
```

**Step 4: Update `watch_project` and `unwatch_project`**

```python
@mcp.tool()
def watch_project(path: str) -> str:
    """Start a file watcher that automatically re-indexes changed .cs files.

    The watcher keeps the LSP process alive between file changes, enabling
    incremental re-indexing without a full index_project call. Use after
    index_project during active development sessions.
    """
    service.watch_project(path)
    return f"Watching {path}"


@mcp.tool()
def unwatch_project(path: str) -> str:
    """Stop the file watcher for the given project path.

    Call this when done with active development to release the LSP process.
    """
    service.unwatch_project(path)
    return f"Stopped watching {path}"
```

**Step 5: Run full unit suite**

```bash
pytest tests/unit/ -v
```
Expected: all PASS

**Step 6: Commit**

```bash
git add src/synapse/mcp/tools.py
git commit -m "docs: update tool descriptions for search_symbols, find_callees, get_context_for, watch/unwatch"
```

---

## Task 9: `search_symbols` namespace + file filter

**Files:**
- Modify: `src/synapse/graph/queries.py:59-72`
- Modify: `src/synapse/service.py:103-104`
- Modify: `tests/unit/test_queries.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_queries.py`:

```python
from synapse.graph.queries import search_symbols as qs_search


def test_search_symbols_namespace_filter():
    node = _node(["Method"], {"full_name": "MyNs.Svc.DoWork", "name": "DoWork"})
    conn = _conn([[node]])
    result = qs_search(conn, "Do", namespace="MyNs.Svc")
    assert len(result) == 1
    cypher = conn.query.call_args[0][0]
    assert "STARTS WITH" in cypher


def test_search_symbols_file_path_filter():
    node = _node(["Method"], {"full_name": "MyNs.Svc.DoWork", "name": "DoWork"})
    conn = _conn([[node]])
    result = qs_search(conn, "Do", file_path="src/Svc.cs")
    assert len(result) == 1
    cypher = conn.query.call_args[0][0]
    assert "file_path" in cypher


def test_search_symbols_combined_filters():
    conn = _conn([])
    qs_search(conn, "Do", kind="Method", namespace="MyNs", file_path="src/Svc.cs")
    cypher = conn.query.call_args[0][0]
    assert "STARTS WITH" in cypher
    assert "file_path" in cypher
    assert "Method" in cypher
```

**Step 2: Run to confirm they fail**

```bash
pytest tests/unit/test_queries.py::test_search_symbols_namespace_filter \
       tests/unit/test_queries.py::test_search_symbols_file_path_filter \
       tests/unit/test_queries.py::test_search_symbols_combined_filters -v
```
Expected: FAIL

**Step 3: Update `search_symbols` in `queries.py`**

```python
def search_symbols(
    conn: GraphConnection,
    query: str,
    kind: str | None = None,
    namespace: str | None = None,
    file_path: str | None = None,
) -> list[dict]:
    if kind and kind not in _VALID_KINDS:
        raise ValueError(
            f"Unknown symbol kind: {kind!r}. Valid values: {sorted(_VALID_KINDS)}"
        )
    label = f":{kind}" if kind else ""
    conditions = ["n.full_name IS NOT NULL", "n.name CONTAINS $query"]
    params: dict = {"query": query}
    if namespace:
        conditions.append("n.full_name STARTS WITH $namespace")
        params["namespace"] = namespace
    if file_path:
        conditions.append("n.file_path = $file_path")
        params["file_path"] = file_path
    where = " AND ".join(conditions)
    rows = conn.query(f"MATCH (n{label}) WHERE {where} RETURN n", params)
    return [r[0] for r in rows]
```

**Step 4: Update `SynapseService.search_symbols` in `service.py`**

```python
def search_symbols(
    self,
    query: str,
    kind: str | None = None,
    namespace: str | None = None,
    file_path: str | None = None,
) -> list[dict]:
    return [_p(item) for item in search_symbols(self._conn, query, kind, namespace, file_path)]
```

**Step 5: Run tests**

```bash
pytest tests/unit/ -v
```
Expected: all PASS

**Step 6: Commit**

```bash
git add src/synapse/graph/queries.py src/synapse/service.py tests/unit/test_queries.py
git commit -m "feat: search_symbols namespace and file_path filters"
```

---

## Task 10: `find_dependencies` depth parameter

**Files:**
- Modify: `src/synapse/graph/queries.py:154-159`
- Modify: `src/synapse/service.py:119-120`
- Modify: `src/synapse/mcp/tools.py`
- Modify: `tests/unit/test_queries.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_queries.py`:

```python
from synapse.graph.queries import find_dependencies as qs_find_deps


def test_find_dependencies_depth_1_is_default():
    conn = _conn([])
    qs_find_deps(conn, "Ns.Cls")
    cypher = conn.query.call_args[0][0]
    assert "*1..1" in cypher or "REFERENCES]->" in cypher  # depth 1


def test_find_dependencies_depth_2_annotates_depth():
    dep1 = _node(["Class"], {"full_name": "Ns.Dep"})
    conn = MagicMock()
    # Variable length query returns (node, path_length) pairs
    conn.query.return_value = [[dep1, 2]]
    result = qs_find_deps(conn, "Ns.Cls", depth=2)
    assert result[0]["depth"] == 2


def test_find_dependencies_depth_capped_at_5():
    conn = _conn([])
    qs_find_deps(conn, "Ns.Cls", depth=99)
    cypher = conn.query.call_args[0][0]
    assert "*1..5" in cypher
```

**Step 2: Run to confirm they fail**

```bash
pytest tests/unit/test_queries.py::test_find_dependencies_depth_1_is_default \
       tests/unit/test_queries.py::test_find_dependencies_depth_2_annotates_depth \
       tests/unit/test_queries.py::test_find_dependencies_depth_capped_at_5 -v
```
Expected: FAIL

**Step 3: Update `find_dependencies` in `queries.py`**

```python
def find_dependencies(conn: GraphConnection, full_name: str, depth: int = 1) -> list[dict]:
    effective_depth = min(depth, 5)
    rows = conn.query(
        f"MATCH p=(n {{full_name: $full_name}})-[:REFERENCES*1..{effective_depth}]->(t) "
        "RETURN t, length(p)",
        {"full_name": full_name},
    )
    return [{"type": row[0], "depth": row[1]} for row in rows]
```

**Step 4: Update `SynapseService.find_dependencies` in `service.py`**

```python
def find_dependencies(self, full_name: str, depth: int = 1) -> list[dict]:
    return [
        {"type": _p(r["type"]), "depth": r["depth"]}
        for r in query_find_dependencies(self._conn, full_name, depth)
    ]
```

**Step 5: Update MCP tool in `tools.py`**

```python
@mcp.tool()
def find_dependencies(full_name: str, depth: int = 1) -> list[dict]:
    """Find field-type dependencies for the given symbol.

    depth: how many hops to traverse (default 1 = direct deps only, max 5).
    Each result includes a 'depth' field indicating how many hops from the root.
    Useful for impact analysis — depth=2 shows transitive dependencies.
    """
    return service.find_dependencies(full_name, depth)
```

**Step 6: Run full unit suite**

```bash
pytest tests/unit/ -v
```
Expected: all PASS

**Step 7: Commit**

```bash
git add src/synapse/graph/queries.py src/synapse/service.py src/synapse/mcp/tools.py tests/unit/test_queries.py
git commit -m "feat: find_dependencies depth parameter with depth annotation on results"
```

---

## Final Verification

```bash
pytest tests/unit/ -v
```
Expected: all tests pass, no regressions.
