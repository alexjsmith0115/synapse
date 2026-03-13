# FalkorDB → Memgraph Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace FalkorDB with Memgraph (via the `neo4j` Python Bolt driver) to gain full Cypher `=~` regex support, while preserving all existing behaviour.

**Architecture:** Single `GraphConnection` class internals are swapped from the FalkorDB Redis client to `neo4j.GraphDatabase.driver()`. Both Memgraph and future Neo4j use the same driver — switching backends is a URL/database-name config change only. The only backend-specific surface is index syntax in `schema.py`, handled via a `dialect` parameter stored on `GraphConnection`.

**Tech Stack:** Python 3.11+, `neo4j>=5.0.0` (Bolt driver), Memgraph (port 7687), pytest

---

## File Map

| File | Change |
|------|--------|
| `pyproject.toml` | Remove `falkordb`, add `neo4j>=5.0.0` |
| `src/synapse/graph/connection.py` | Full rewrite: neo4j Bolt driver, `dialect` storage, `close()` method |
| `src/synapse/graph/schema.py` | Remove `redis.exceptions` import; add `dialect` param; Memgraph/Neo4j index syntax; drop try/except (idempotent) |
| `src/synapse/graph/lookups.py` | Three fixes: `node.id` → `node.element_id` (3 sites), `repo.properties.get(...)` → `repo.get(...)` |
| `src/synapse/graph/analysis.py` | `dict(zip(range(len(r)), r))` → `dict(r)` in `audit_architecture` |
| `src/synapse/graph/traversal.py` | Update module docstring (remove FalkorDB attribution) |
| `src/synapse/service.py` | Fix `_p()` guard + body; fix `execute_query` inline guard (line 177) |
| `tests/unit/graph/test_schema.py` | Remove `ResponseError` test; update index syntax assertions |
| `tests/unit/test_queries.py` | Replace `FalkorNode` mock with `_MockNode`; update dedup test |
| `tests/unit/test_service.py` | Replace `FalkorNode` mock with `_MockNode` |
| `tests/integration/conftest.py` | Update `GraphConnection.create(graph_name=...)` → `GraphConnection.create(database="memgraph")`; update docstring |
| `tests/integration/test_mcp_tools.py` | Update module docstring (FalkorDB → Memgraph, 6379 → 7687) |
| `tests/integration/test_cli_commands.py` | Update module docstring (FalkorDB → Memgraph, 6379 → 7687) |
| `README.md` | Update all FalkorDB/6379 references (quick-start, prerequisites, integration test instructions) |
| `CLAUDE.md` | Update Docker command (port 6379→7687, image falkordb→memgraph) |

**Not changed:** `nodes.py`, `edges.py` (write-only, no result access). `traversal.py` result access (integer positional access works unchanged on `neo4j.Record`). `analysis.py` scalar column access (same).

**Important execution note:** `pip install -e ".[dev]"` installs `neo4j` but does **not** automatically uninstall `falkordb`. This means `falkordb` and `redis` remain importable throughout all tasks. This is intentional — it lets you update test files at any point without import errors. An explicit `pip uninstall falkordb -y` step is deferred to Task 6 after all tests pass.

---

## Background: How neo4j.Record differs from FalkorDB result_set

FalkorDB returns `result.result_set` — a `list[list]` where each row is a Python list of values.

`neo4j.Record` is a tuple subclass that also implements the Mapping protocol:
- `record[0]` — positional access (works, same as before) ✓
- `record["col_name"]` — named access ✓
- `dict(record)` — returns `{"col_name": value, ...}` (named dict) ✓
- `for v in record` — yields VALUES (same as list iteration) ✓

**Only two patterns genuinely break:**
1. `node.properties` — FalkorDB nodes have a `.properties` dict; neo4j nodes do not. Use `dict(node)` or `node["key"]`.
2. `node.id` — deprecated in neo4j 5.x driver. Use `node.element_id` (a string).

---

## Chunk 1: Connection, Schema, Dependency

### Task 1: Swap dependency and rewrite `connection.py`

**Files:**
- Modify: `pyproject.toml`
- Rewrite: `src/synapse/graph/connection.py`
- Test: `tests/unit/graph/test_connection.py` (check if it exists; if not, no new test needed — connection is covered by schema tests)

- [ ] **Step 1: Write a failing test for the new connection interface**

```python
# tests/unit/graph/test_connection.py  (create if it doesn't exist)
from unittest.mock import MagicMock, patch
from synapse.graph.connection import GraphConnection


def test_create_returns_graph_connection():
    mock_driver = MagicMock()
    # Patch at the module level where GraphDatabase is imported
    with patch("synapse.graph.connection.GraphDatabase") as mock_gdb:
        mock_gdb.driver.return_value = mock_driver
        conn = GraphConnection.create(host="localhost", port=7687)
    assert isinstance(conn, GraphConnection)
    mock_gdb.driver.assert_called_once_with("bolt://localhost:7687", auth=("", ""))


def test_query_returns_records():
    mock_driver = MagicMock()
    mock_records = [MagicMock(), MagicMock()]
    mock_driver.execute_query.return_value = (mock_records, MagicMock(), [])
    conn = GraphConnection(mock_driver, database="memgraph", dialect="memgraph")
    result = conn.query("MATCH (n) RETURN n")
    assert result == mock_records


def test_execute_returns_none():
    mock_driver = MagicMock()
    mock_driver.execute_query.return_value = ([], MagicMock(), [])
    conn = GraphConnection(mock_driver, database="memgraph", dialect="memgraph")
    result = conn.execute("MERGE (n:Foo {id: $id})", {"id": 1})
    assert result is None


def test_close_calls_driver_close():
    mock_driver = MagicMock()
    conn = GraphConnection(mock_driver, database="memgraph", dialect="memgraph")
    conn.close()
    mock_driver.close.assert_called_once()


def test_dialect_stored_on_instance():
    mock_driver = MagicMock()
    conn = GraphConnection(mock_driver, database="memgraph", dialect="neo4j")
    assert conn.dialect == "neo4j"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate && pytest tests/unit/graph/test_connection.py -v
```

Expected: ImportError or AttributeError — `GraphConnection` doesn't match the new interface yet.

- [ ] **Step 3: Rewrite `connection.py`**

Note: `GraphDatabase` is imported at module level (not lazily) so unit tests can patch `synapse.graph.connection.GraphDatabase`.

```python
from __future__ import annotations

from typing import Literal

from neo4j import GraphDatabase


class GraphConnection:
    """Wraps a neo4j Driver, providing query and execute operations."""

    def __init__(
        self,
        driver,
        database: str = "memgraph",
        dialect: Literal["memgraph", "neo4j"] = "memgraph",
    ) -> None:
        self._driver = driver
        self._database = database
        self._dialect = dialect

    @property
    def dialect(self) -> str:
        return self._dialect

    @classmethod
    def create(
        cls,
        host: str = "localhost",
        port: int = 7687,
        database: str = "memgraph",
        dialect: Literal["memgraph", "neo4j"] = "memgraph",
    ) -> GraphConnection:
        driver = GraphDatabase.driver(f"bolt://{host}:{port}", auth=("", ""))
        return cls(driver, database=database, dialect=dialect)

    def query(self, cypher: str, params: dict | None = None) -> list:
        records, _, _ = self._driver.execute_query(
            cypher, params or {}, database_=self._database
        )
        return records

    def execute(self, cypher: str, params: dict | None = None) -> None:
        self._driver.execute_query(
            cypher, params or {}, database_=self._database
        )

    def close(self) -> None:
        self._driver.close()
```

- [ ] **Step 4: Update `pyproject.toml`**

Replace:
```toml
"falkordb>=1.0.0",
```
With:
```toml
"neo4j>=5.0.0",
```

- [ ] **Step 5: Update `tests/integration/conftest.py`**

Line 60 currently calls `GraphConnection.create(graph_name="synapse_integration_test")`. The `graph_name` parameter is removed in the new interface. Replace with:

```python
conn = GraphConnection.create(database="memgraph")
```

- [ ] **Step 6: Install new dependency**

```bash
source .venv/bin/activate && pip install -e ".[dev]"
```

Expected: neo4j installs, falkordb not listed.

- [ ] **Step 7: Run connection tests**

```bash
source .venv/bin/activate && pytest tests/unit/graph/test_connection.py -v
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/synapse/graph/connection.py tests/unit/graph/test_connection.py tests/integration/conftest.py
git commit -m "feat: replace FalkorDB with neo4j Bolt driver in GraphConnection"
```

---

### Task 2: Update `schema.py` and its tests

**Files:**
- Modify: `src/synapse/graph/schema.py`
- Modify: `tests/unit/graph/test_schema.py`

**Background:** The existing `_INDICES` strings use Neo4j-style syntax (`CREATE INDEX FOR (n:Label) ON (n.prop)`). For `dialect="neo4j"` these strings are used as-is. For `dialect="memgraph"` the function generates Memgraph-style statements (`CREATE INDEX ON :Label(prop)`) at runtime. Memgraph's `CREATE INDEX ON` is idempotent so the `try/except ResponseError` guard is dropped.

- [ ] **Step 1: Update `test_schema.py` — remove the ResponseError test, add dialect tests**

Replace the full file:

```python
from unittest.mock import MagicMock
from synapse.graph.schema import ensure_schema


def test_ensure_schema_memgraph_creates_indices() -> None:
    conn = MagicMock()
    conn.dialect = "memgraph"
    ensure_schema(conn)
    calls = [c[0][0] for c in conn.execute.call_args_list]
    # Memgraph syntax: CREATE INDEX ON :Label(prop)
    assert any("CREATE INDEX ON :File" in c for c in calls)
    assert any("CREATE INDEX ON :Class" in c for c in calls)
    assert any("CREATE INDEX ON :Method" in c for c in calls)


def test_ensure_schema_neo4j_creates_indices() -> None:
    conn = MagicMock()
    conn.dialect = "neo4j"
    ensure_schema(conn)
    calls = [c[0][0] for c in conn.execute.call_args_list]
    # Neo4j syntax: CREATE INDEX FOR (n:Label) ON (n.prop)
    assert any("CREATE INDEX FOR (n:File)" in c for c in calls)
    assert any("CREATE INDEX FOR (n:Class)" in c for c in calls)
    assert any("CREATE INDEX FOR (n:Method)" in c for c in calls)


def test_schema_includes_package_index() -> None:
    conn = MagicMock()
    conn.dialect = "memgraph"  # must be set explicitly — MagicMock default is not a valid dialect
    ensure_schema(conn)
    calls = [c[0][0] for c in conn.execute.call_args_list]
    assert any(":Package" in c for c in calls)


def test_schema_includes_interface_index() -> None:
    conn = MagicMock()
    conn.dialect = "memgraph"
    ensure_schema(conn)
    calls = [c[0][0] for c in conn.execute.call_args_list]
    assert any(":Interface" in c for c in calls)


def test_schema_does_not_include_namespace_index() -> None:
    conn = MagicMock()
    conn.dialect = "memgraph"
    ensure_schema(conn)
    calls = [c[0][0] for c in conn.execute.call_args_list]
    assert not any(":Namespace" in c for c in calls)


def test_schema_correct_number_of_indices() -> None:
    """One index per node type: Repository, Directory, File, Package,
    Class, Interface, Method, Property, Field = 9 total."""
    conn = MagicMock()
    conn.dialect = "memgraph"
    ensure_schema(conn)
    assert conn.execute.call_count == 9
```

- [ ] **Step 2: Run tests to see them fail**

```bash
source .venv/bin/activate && pytest tests/unit/graph/test_schema.py -v
```

Expected: failures because `ensure_schema` still has the old signature and redis import.

- [ ] **Step 3: Rewrite `schema.py`**

```python
from __future__ import annotations

from typing import Literal

from synapse.graph.connection import GraphConnection

# (label, property) pairs — source of truth for all index definitions
_INDEX_DEFS = [
    ("Repository", "path"),
    ("Directory", "path"),
    ("File", "path"),
    ("Package", "full_name"),
    ("Class", "full_name"),
    ("Interface", "full_name"),
    ("Method", "full_name"),
    ("Property", "full_name"),
    ("Field", "full_name"),
]


def _make_index_statement(label: str, prop: str, dialect: Literal["memgraph", "neo4j"]) -> str:
    if dialect == "neo4j":
        return f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
    return f"CREATE INDEX ON :{label}({prop})"


def ensure_schema(conn: GraphConnection) -> None:
    """Create graph indices. Idempotent on Memgraph; safe to re-run."""
    for label, prop in _INDEX_DEFS:
        conn.execute(_make_index_statement(label, prop, conn.dialect))
```

- [ ] **Step 4: Run schema tests**

```bash
source .venv/bin/activate && pytest tests/unit/graph/test_schema.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run the full unit test suite to check for regressions**

```bash
source .venv/bin/activate && pytest tests/unit/ -v
```

Expected: failures only in `test_queries.py` and `test_service.py` (FalkorNode import errors — addressed in Tasks 3–4).

- [ ] **Step 6: Commit**

```bash
git add src/synapse/graph/schema.py tests/unit/graph/test_schema.py
git commit -m "feat: add dialect-aware index syntax to schema.py, drop redis dependency"
```

---

## Chunk 2: _p() and Service Layer

### Task 3: Fix `_p()` and `execute_query` inline guard in `service.py`

**Files:**
- Modify: `src/synapse/service.py` (lines 29–36 and line 177)
- Modify: `tests/unit/test_service.py`

**Background:**
- `_p(node)` currently guards with `hasattr(node, "properties")`. On neo4j nodes this is `False`, causing `_p()` to return the raw `Node` object instead of a dict. Fix: guard on `hasattr(node, "element_id")` (present on neo4j graph nodes but not plain dicts).
- The body changes from `dict(node.properties)` to `dict(node)` (neo4j Node implements Mapping).
- `execute_query` at line 177 has the same inline `hasattr(cell, "properties")` guard — fix identically.
- Test mocks: replace `FalkorNode` with a `_MockNode` that supports the neo4j Node interface.

- [ ] **Step 1: Define `_MockNode` and update test helpers in `test_service.py`**

At the top of `test_service.py`, replace:

```python
from falkordb.node import Node as FalkorNode
```

And replace the `_node()` helper:

```python
# Remove: from falkordb.node import Node as FalkorNode

class _MockNode:
    """Minimal neo4j graph.Node stand-in for unit tests."""
    def __init__(self, labels: list[str], props: dict, element_id: str | None = None) -> None:
        self._props = props
        self.labels = frozenset(labels)
        self.element_id = element_id or str(id(self))

    def keys(self): return list(self._props.keys())
    def values(self): return list(self._props.values())
    def items(self): return list(self._props.items())
    def __getitem__(self, key): return self._props[key]
    def __iter__(self): return iter(self._props)
    def __len__(self): return len(self._props)
    def get(self, key, default=None): return self._props.get(key, default)


def _node(labels: list[str], props: dict) -> _MockNode:
    return _MockNode(labels, props)
```

Also update the `test_p_*` tests:

```python
def test_p_extracts_properties_and_labels_from_neo4j_node():
    node = _node(["Method"], {"full_name": "A.B", "signature": "B() : void"})
    result = _p(node)
    assert result == {"full_name": "A.B", "signature": "B() : void", "_labels": ["Method"]}


def test_p_passes_through_plain_dict():
    d = {"full_name": "A.B"}
    assert _p(d) is d
```

- [ ] **Step 2: Run the failing test to confirm the issue**

```bash
source .venv/bin/activate && pytest tests/unit/test_service.py::test_p_extracts_properties_and_labels_from_neo4j_node -v
```

Expected: FAIL — `_p()` returns raw node instead of dict (guard evaluates False for `_MockNode` which lacks `.properties`).

- [ ] **Step 3: Fix `_p()` and the `execute_query` inline guard in `service.py`**

Replace lines 29–36 (the `_p` function):

```python
def _p(node) -> dict:
    """Extract properties from a neo4j graph Node (including labels) or pass through a plain dict."""
    if hasattr(node, "element_id"):
        result = dict(node)
        if node.labels:
            result["_labels"] = list(node.labels)
        return result
    return node
```

Replace line 177 (the `execute_query` cell check):

```python
    def execute_query(self, cypher: str) -> list[dict]:
        raw = execute_readonly_query(self._conn, cypher)
        return [{"row": [_p(cell) if hasattr(cell, "element_id") else cell for cell in row]} for row in raw]
```

- [ ] **Step 4: Run service tests**

```bash
source .venv/bin/activate && pytest tests/unit/test_service.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/synapse/service.py tests/unit/test_service.py
git commit -m "fix: update _p() and execute_query to use neo4j node interface (element_id, dict(node))"
```

---

## Chunk 3: Lookups, Analysis, Traversal

### Task 4: Fix `lookups.py` and update `test_queries.py` mocks

**Files:**
- Modify: `src/synapse/graph/lookups.py`
- Modify: `tests/unit/test_queries.py`

**Exact changes in `lookups.py`:**
1. `list_summarized` (lines 180–186): `node.id` → `node.element_id`; `seen: set[int]` → `seen: set[str]`
2. `find_callers` (line 84): `node.id if hasattr(node, "id") else node.get("full_name")` → `node.element_id`
3. `find_callees` (line 111): same pattern → `node.element_id`
4. `get_index_status` (line 214): `repo.properties.get("last_indexed")` → `repo.get("last_indexed")`

- [ ] **Step 1: Define `_MockNode` and update test helpers in `test_queries.py`**

Replace the top of `test_queries.py`:

```python
# Remove: from falkordb.node import Node as FalkorNode

class _MockNode:
    """Minimal neo4j graph.Node stand-in for unit tests."""
    def __init__(self, labels: list[str], props: dict, element_id: str | None = None) -> None:
        self._props = props
        self.labels = frozenset(labels)
        self.element_id = element_id or str(id(self))

    def keys(self): return list(self._props.keys())
    def values(self): return list(self._props.values())
    def items(self): return list(self._props.items())
    def __getitem__(self, key): return self._props[key]
    def __iter__(self): return iter(self._props)
    def __len__(self): return len(self._props)
    def get(self, key, default=None): return self._props.get(key, default)


def _node(labels, props, element_id=None):
    return _MockNode(labels, props, element_id=element_id)
```

Also update `test_list_summarized_deduplicates` to use `element_id`:

```python
def test_list_summarized_deduplicates():
    # Two distinct Python objects with the same element_id simulate two traversal
    # paths to the same graph node — the real production scenario
    shared_id = "elem-42"
    node_a = _node(["Class", "Summarized"], {"full_name": "A.B"}, element_id=shared_id)
    node_b = _node(["Class", "Summarized"], {"full_name": "A.B"}, element_id=shared_id)
    assert node_a is not node_b          # different objects
    assert node_a.element_id == node_b.element_id  # same graph node
    conn = _conn([[node_a], [node_b]])
    result = list_summarized(conn)
    assert len(result) == 1
```

Also update `test_find_callers_deduplicates_across_both_queries`:

```python
def test_find_callers_deduplicates_across_both_queries():
    shared_id = "elem-5"
    shared_node_a = _node(["Method"], {"full_name": "A.Both"}, element_id=shared_id)
    shared_node_b = _node(["Method"], {"full_name": "A.Both"}, element_id=shared_id)
    conn = MagicMock()
    conn.query.side_effect = [[[shared_node_a]], [[shared_node_b]]]
    result = find_callers(conn, "Svc.DoWork")
    assert len(result) == 1
```

- [ ] **Step 2: Run failing tests to confirm the issues**

```bash
source .venv/bin/activate && pytest tests/unit/test_queries.py::test_list_summarized_deduplicates tests/unit/test_queries.py::test_find_callers_deduplicates_across_both_queries -v
```

Expected: FAIL — `node.id` not found on `_MockNode`, deduplication broken.

- [ ] **Step 3: Fix `lookups.py`**

Change **`list_summarized`** (the `seen` set and the dedup key):

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
    seen: set[str] = set()
    result = []
    for r in rows:
        node = r[0]
        if node.element_id not in seen:
            seen.add(node.element_id)
            result.append(node)
    return result
```

Change **`find_callers`** deduplication key (line 84):

```python
        key = node.element_id
```

Change **`find_callees`** deduplication key (line 111):

```python
        key = node.element_id
```

Change **`get_index_status`** property access (line 214):

```python
        "last_indexed": repo.get("last_indexed"),
```

- [ ] **Step 4: Run all query tests**

```bash
source .venv/bin/activate && pytest tests/unit/test_queries.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full unit suite**

```bash
source .venv/bin/activate && pytest tests/unit/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/synapse/graph/lookups.py tests/unit/test_queries.py
git commit -m "fix: use node.element_id for deduplication and node.get() for property access"
```

---

### Task 5: Fix `analysis.py` and `traversal.py`

**Files:**
- Modify: `src/synapse/graph/analysis.py` (line 158)
- Modify: `src/synapse/graph/traversal.py` (module docstring lines 1–11)

**Background:** `audit_architecture` currently uses integer-keyed dicts `{0: val, 1: val}`. Changing to `dict(r)` gives named keys `{"ctrl.name": val, "m.name": val}` — more useful to callers. Note: this is a behaviour change to the `audit_architecture` return value (key format changes). The traversal docstring change is cosmetic only.

- [ ] **Step 1: Write a failing test for named violation keys**

Add to `tests/unit/graph/test_analysis.py` (create if needed):

```python
from unittest.mock import MagicMock
from synapse.graph.analysis import audit_architecture


def test_audit_architecture_violations_have_named_keys():
    """Violations should use column names as keys, not integers."""
    # Simulate a neo4j.Record: dict() uses keys() + __getitem__, not __iter__
    mock_row = MagicMock()
    mock_row.keys.return_value = ["ctrl.name", "m.name", "db.full_name"]
    mock_row.__getitem__ = lambda self, k: {"ctrl.name": "MyCtrl", "m.name": "MyMethod", "db.full_name": "SomeDb.Save"}[k]

    conn = MagicMock()
    conn.query.return_value = [mock_row]

    result = audit_architecture(conn, "layering_violations")
    assert len(result["violations"]) == 1
    violation = result["violations"][0]
    assert 0 not in violation, "violations must not use integer keys"
    assert "ctrl.name" in violation, "violations must use column names as keys"
    assert violation["ctrl.name"] == "MyCtrl"
```

- [ ] **Step 2: Run to see it fail**

```bash
source .venv/bin/activate && pytest tests/unit/graph/test_analysis.py::test_audit_architecture_violations_have_named_keys -v
```

Expected: FAIL — violation dict has integer key `0`.

- [ ] **Step 3: Fix `audit_architecture` in `analysis.py`**

Change line 158:

```python
    violations = [dict(r) for r in rows]
```

- [ ] **Step 4: Update `traversal.py` module docstring**

Replace lines 1–11:

```python
"""Multi-hop call chain traversal queries.

These queries follow CALLS and DISPATCHES_TO edges across multiple hops.
DISPATCHES_TO (iface_method → impl_method) is the traversal-friendly inverse
of IMPLEMENTS, written at index time so paths can cross interface dispatch
boundaries without mixed-direction variable-length patterns.

Graph databases do not support parameterized variable-length relationship bounds,
so the depth integer is inlined into the Cypher string after validation
(must be int, clamped 1-10).
"""
```

- [ ] **Step 5: Run analysis test**

```bash
source .venv/bin/activate && pytest tests/unit/graph/test_analysis.py -v
```

Expected: all PASS.

- [ ] **Step 6: Run full unit suite**

```bash
source .venv/bin/activate && pytest tests/unit/ -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/synapse/graph/analysis.py src/synapse/graph/traversal.py tests/unit/graph/test_analysis.py
git commit -m "fix: use dict(r) for named violation keys in audit_architecture; update traversal docstring"
```

---

## Chunk 4: Documentation

### Task 6: Update documentation and remove falkordb

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `tests/integration/conftest.py` (docstring)
- Modify: `tests/integration/test_mcp_tools.py` (module docstring)
- Modify: `tests/integration/test_cli_commands.py` (module docstring)

- [ ] **Step 1: Update `CLAUDE.md` Docker command**

Find:
```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb:latest  # start FalkorDB
```
Replace with:
```bash
docker run -p 7687:7687 -it --rm memgraph/memgraph:latest  # start Memgraph (in-memory; data lost on restart — tests always re-index from scratch)
```

- [ ] **Step 2: Update `README.md`**

Find and replace all occurrences of:
- `falkordb/falkordb:latest` → `memgraph/memgraph:latest`
- `6379:6379` → `7687:7687`
- `FalkorDB` → `Memgraph`
- `localhost:6379` → `localhost:7687`

- [ ] **Step 3: Update integration test module docstrings**

In `tests/integration/conftest.py`, `tests/integration/test_mcp_tools.py`, and `tests/integration/test_cli_commands.py`, update any docstring or comment that says "Requires FalkorDB on localhost:6379" to "Requires Memgraph on localhost:7687".

- [ ] **Step 4: Verify no remaining FalkorDB references in tracked source files**

```bash
grep -r "falkordb\|FalkorDB" --include="*.py" --include="*.md" --include="*.toml" . | grep -v ".venv" | grep -v "__pycache__" | grep -v "docs/superpowers"
```

Expected: zero matches (docs/specs are excluded as reference material).

- [ ] **Step 5: Uninstall falkordb**

```bash
source .venv/bin/activate && pip uninstall falkordb -y
```

- [ ] **Step 6: Run full unit test suite to confirm no remaining falkordb imports**

```bash
source .venv/bin/activate && pytest tests/unit/ -v
```

Expected: all PASS, no ImportError from falkordb or redis.

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md README.md tests/integration/conftest.py tests/integration/test_mcp_tools.py tests/integration/test_cli_commands.py
git commit -m "docs: update all FalkorDB references to Memgraph (port 6379→7687); uninstall falkordb"
```

---

## Integration Test Verification (manual, requires Docker)

Once Memgraph is running:

```bash
docker run -p 7687:7687 -it --rm memgraph/memgraph:latest
```

In another terminal:

```bash
source .venv/bin/activate && pytest tests/integration/ -v -m integration
source .venv/bin/activate && pytest tests/mcp/ -v -m integration
```

Key things to verify:
- Schema creation runs without error
- `=~` regex operator works in `find_callers(exclude_test_callers=True)` queries
- `get_index_status` returns correct `last_indexed` value
- `audit_architecture` violations have named keys in output
