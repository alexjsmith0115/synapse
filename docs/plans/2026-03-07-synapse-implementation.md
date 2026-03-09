# Synapse Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build Synapse — an LSP-powered, FalkorDB-backed MCP tool that creates an accurate, queryable graph of a C# codebase including implicit dependencies (DI, interface implementations, abstract overrides).

**Architecture:** Eager indexer — LSP runs at index time, writes everything to FalkorDB, then shuts down. File watcher keeps LSP alive and triggers incremental re-indexing on change. MCP server and CLI are thin consumers of a shared service layer; all business logic lives in `graph/` and `indexer/`.

**Tech Stack:** Python 3.11+, FalkorDB (via `falkordb` client), solidlsp (copied from Serena, MIT), MCP (via `mcp` library), Typer (CLI), watchdog (file watching), pytest + pytest-timeout (testing), sensai-utils + overrides (solidlsp dependencies)

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `pytest.ini`
- Create: `.gitignore`
- Create: `src/synapse/__init__.py`
- Create: `src/synapse/graph/__init__.py`
- Create: `src/synapse/indexer/__init__.py`
- Create: `src/synapse/watcher/__init__.py`
- Create: `src/synapse/mcp/__init__.py`
- Create: `src/synapse/cli/__init__.py`
- Create: `src/synapse/util/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`

**Step 1: Create pyproject.toml**

```toml
[build-system]
build-backend = "hatchling.build"
requires = ["hatchling"]

[project]
name = "synapse"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "falkordb>=1.0.0",
    "mcp>=1.0.0",
    "typer>=0.12.0",
    "watchdog>=4.0.0",
    "pydantic>=2.0.0",
    "sensai-utils>=1.5.0",
    "overrides>=7.7.0",
    "pathspec>=0.12.1",
    "psutil>=7.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-timeout>=2.0.0",
]

[project.scripts]
synapse = "synapse.cli:app"
synapse-mcp = "synapse.mcp.server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/synapse", "src/solidlsp"]
```

**Step 2: Create pytest.ini**

```ini
[pytest]
timeout = 10
timeout_method = thread
testpaths = tests
```

**Step 3: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
dist/
*.egg-info/
.env
```

**Step 4: Create all `__init__.py` files (empty)**

```bash
mkdir -p src/synapse/{graph,indexer,watcher,mcp,cli,util}
mkdir -p tests/{unit,integration,mcp}
touch src/synapse/__init__.py src/synapse/graph/__init__.py src/synapse/indexer/__init__.py
touch src/synapse/watcher/__init__.py src/synapse/mcp/__init__.py src/synapse/cli/__init__.py
touch src/synapse/util/__init__.py
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py tests/mcp/__init__.py
```

**Step 5: Install in dev mode**

```bash
pip install -e ".[dev]"
```

Expected: package installs without errors.

**Step 6: Verify pytest runs**

```bash
pytest --collect-only
```

Expected: `no tests ran` (no tests yet), no errors.

**Step 7: Commit**

```bash
git add pyproject.toml pytest.ini .gitignore src/ tests/
git commit -m "feat: initial project scaffolding for Synapse"
```

---

## Task 2: Copy and Adapt solidlsp

solidlsp is copied from Serena (MIT License, Copyright 2025 Oraios AI). It has cross-dependencies into `serena.util` and `sensai-utils` that must be resolved.

**Files:**
- Create: `src/solidlsp/` (copied from `/Users/alex/Dev/opensource/serena/src/solidlsp/`)
- Create: `src/synapse/util/file_system.py` (from serena)
- Create: `src/synapse/util/text_utils.py` (from serena)
- Create: `src/synapse/util/dotnet.py` (from serena)
- Create: `NOTICE` (attribution)

**Step 1: Copy solidlsp**

```bash
cp -r /Users/alex/Dev/opensource/serena/src/solidlsp src/solidlsp
```

**Step 2: Remove unused language servers (keep only csharp + common)**

```bash
cd src/solidlsp/language_servers
# keep: csharp_language_server.py, common.py, omnisharp/ directory
# remove everything else
ls | grep -v -E "^(csharp_language_server|common|omnisharp)$" | xargs rm -rf
```

**Step 3: Copy required serena.util files**

```bash
cp /Users/alex/Dev/opensource/serena/src/serena/util/file_system.py src/synapse/util/file_system.py
cp /Users/alex/Dev/opensource/serena/src/serena/util/text_utils.py src/synapse/util/text_utils.py
cp /Users/alex/Dev/opensource/serena/src/serena/util/dotnet.py src/synapse/util/dotnet.py
```

**Step 4: Fix import paths — replace `serena.util` with `synapse.util` throughout solidlsp**

```bash
find src/solidlsp -name "*.py" -exec sed -i '' 's/from serena\.util\./from synapse.util./g' {} +
find src/solidlsp -name "*.py" -exec sed -i '' 's/import serena\.util\./import synapse.util./g' {} +
```

**Step 5: Check for any remaining serena imports**

```bash
grep -r "serena" src/solidlsp/
```

Expected: no output. If any remain, fix them manually.

**Step 6: Create NOTICE file**

```
solidlsp — copied from Serena (https://github.com/oraios/serena)
MIT License, Copyright (c) 2025 Oraios AI
```

**Step 7: Verify solidlsp imports**

```python
# run in python shell
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
print("solidlsp imports OK")
```

Expected: prints "solidlsp imports OK" with no errors.

**Step 8: Commit**

```bash
git add src/solidlsp/ src/synapse/util/ NOTICE
git commit -m "feat: copy solidlsp from Serena (MIT) and adapt imports for Synapse"
```

---

## Task 3: Graph Connection Abstraction

**Files:**
- Create: `src/synapse/graph/connection.py`
- Create: `tests/unit/graph/test_connection.py`

**Step 1: Write the failing test**

```python
# tests/unit/graph/test_connection.py
from unittest.mock import MagicMock, patch
from synapse.graph.connection import GraphConnection


def test_query_returns_result_set() -> None:
    mock_graph = MagicMock()
    mock_result = MagicMock()
    mock_result.result_set = [["row1"], ["row2"]]
    mock_graph.query.return_value = mock_result

    conn = GraphConnection(mock_graph)
    result = conn.query("MATCH (n) RETURN n")

    assert result == [["row1"], ["row2"]]
    mock_graph.query.assert_called_once_with("MATCH (n) RETURN n", {})


def test_query_passes_params() -> None:
    mock_graph = MagicMock()
    mock_graph.query.return_value = MagicMock(result_set=[])

    conn = GraphConnection(mock_graph)
    conn.query("MATCH (n {path: $p}) RETURN n", {"p": "/foo"})

    mock_graph.query.assert_called_once_with("MATCH (n {path: $p}) RETURN n", {"p": "/foo"})


def test_execute_calls_graph_query() -> None:
    mock_graph = MagicMock()

    conn = GraphConnection(mock_graph)
    conn.execute("CREATE (n:File {path: $p})", {"p": "/foo"})

    mock_graph.query.assert_called_once_with("CREATE (n:File {path: $p})", {"p": "/foo"})
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/graph/test_connection.py -v
```

Expected: `ModuleNotFoundError: No module named 'synapse.graph.connection'`

**Step 3: Write the implementation**

```python
# src/synapse/graph/connection.py
from __future__ import annotations

from typing import Any


class GraphConnection:
    """Wraps a FalkorDB Graph object, providing query and execute operations."""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    @classmethod
    def create(cls, host: str = "localhost", port: int = 6379, graph_name: str = "synapse") -> GraphConnection:
        from falkordb import FalkorDB

        db = FalkorDB(host=host, port=port)
        return cls(db.select_graph(graph_name))

    def query(self, cypher: str, params: dict | None = None) -> list:
        result = self._graph.query(cypher, params or {})
        return result.result_set

    def execute(self, cypher: str, params: dict | None = None) -> None:
        self._graph.query(cypher, params or {})
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/graph/test_connection.py -v
```

Expected: 3 PASSED

**Step 5: Commit**

```bash
git add src/synapse/graph/connection.py tests/unit/graph/
git commit -m "feat: add GraphConnection abstraction over FalkorDB"
```

---

## Task 4: Graph Schema

**Files:**
- Create: `src/synapse/graph/schema.py`
- Create: `tests/unit/graph/test_schema.py`

**Step 1: Write the failing test**

```python
# tests/unit/graph/test_schema.py
from unittest.mock import MagicMock, call
from synapse.graph.schema import ensure_schema


def test_ensure_schema_creates_indices() -> None:
    mock_conn = MagicMock()
    ensure_schema(mock_conn)
    calls = [str(c) for c in mock_conn.execute.call_args_list]
    # Verify at least one index per major node type
    assert any("File" in c for c in calls)
    assert any("Class" in c for c in calls)
    assert any("Method" in c for c in calls)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/graph/test_schema.py -v
```

Expected: `ImportError`

**Step 3: Write the implementation**

```python
# src/synapse/graph/schema.py
from synapse.graph.connection import GraphConnection

_INDICES = [
    "CREATE INDEX FOR (n:Repository) ON (n.path)",
    "CREATE INDEX FOR (n:Directory) ON (n.path)",
    "CREATE INDEX FOR (n:File) ON (n.path)",
    "CREATE INDEX FOR (n:Namespace) ON (n.full_name)",
    "CREATE INDEX FOR (n:Class) ON (n.full_name)",
    "CREATE INDEX FOR (n:Method) ON (n.full_name)",
    "CREATE INDEX FOR (n:Property) ON (n.full_name)",
    "CREATE INDEX FOR (n:Field) ON (n.full_name)",
]


def ensure_schema(conn: GraphConnection) -> None:
    """Create graph indices. Safe to call multiple times — FalkorDB ignores duplicate index creation."""
    for statement in _INDICES:
        conn.execute(statement)
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/graph/test_schema.py -v
```

Expected: 1 PASSED

**Step 5: Commit**

```bash
git add src/synapse/graph/schema.py tests/unit/graph/test_schema.py
git commit -m "feat: add FalkorDB schema with indices for all node types"
```

---

## Task 5: Graph Node Upserts

**Files:**
- Create: `src/synapse/graph/nodes.py`
- Create: `tests/unit/graph/test_nodes.py`

**Step 1: Write the failing tests**

```python
# tests/unit/graph/test_nodes.py
from unittest.mock import MagicMock
from synapse.graph.nodes import (
    upsert_repository, upsert_directory, upsert_file,
    upsert_namespace, upsert_class, upsert_method,
    upsert_property, upsert_field, delete_file_nodes,
    set_summary, remove_summary,
)


def _conn() -> MagicMock:
    return MagicMock()


def test_upsert_repository_calls_merge() -> None:
    conn = _conn()
    upsert_repository(conn, "/proj", "csharp")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "Repository" in cypher
    assert params["path"] == "/proj"
    assert params["language"] == "csharp"


def test_upsert_class_includes_kind() -> None:
    conn = _conn()
    upsert_class(conn, "MyNs.MyClass", "MyClass", "class")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "Class" in cypher
    assert params["kind"] == "class"


def test_upsert_method_includes_flags() -> None:
    conn = _conn()
    upsert_method(conn, "MyNs.MyClass.MyMethod()", "MyMethod", "void MyMethod()", is_abstract=True, is_static=False)
    _, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert params["is_abstract"] is True
    assert params["is_static"] is False


def test_delete_file_nodes_uses_file_path() -> None:
    conn = _conn()
    delete_file_nodes(conn, "/proj/src/Foo.cs")
    cypher = conn.execute.call_args[0][0]
    assert "File" in cypher


def test_set_summary_adds_summarized_label() -> None:
    conn = _conn()
    set_summary(conn, "MyNs.MyClass", "This class handles auth.")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "Summarized" in cypher
    assert params["content"] == "This class handles auth."


def test_remove_summary_strips_label_and_properties() -> None:
    conn = _conn()
    remove_summary(conn, "MyNs.MyClass")
    cypher = conn.execute.call_args[0][0]
    assert "REMOVE" in cypher
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/graph/test_nodes.py -v
```

Expected: `ImportError`

**Step 3: Write the implementation**

```python
# src/synapse/graph/nodes.py
from datetime import datetime, timezone

from synapse.graph.connection import GraphConnection


def upsert_repository(conn: GraphConnection, path: str, language: str) -> None:
    conn.execute(
        "MERGE (n:Repository {path: $path}) SET n.language = $language, n.last_indexed = $ts",
        {"path": path, "language": language, "ts": _now()},
    )


def upsert_directory(conn: GraphConnection, path: str, name: str) -> None:
    conn.execute(
        "MERGE (n:Directory {path: $path}) SET n.name = $name",
        {"path": path, "name": name},
    )


def upsert_file(conn: GraphConnection, path: str, name: str, language: str) -> None:
    conn.execute(
        "MERGE (n:File {path: $path}) SET n.name = $name, n.language = $language, n.last_indexed = $ts",
        {"path": path, "name": name, "language": language, "ts": _now()},
    )


def upsert_namespace(conn: GraphConnection, full_name: str, name: str) -> None:
    conn.execute(
        "MERGE (n:Namespace {full_name: $full_name}) SET n.name = $name",
        {"full_name": full_name, "name": name},
    )


def upsert_class(conn: GraphConnection, full_name: str, name: str, kind: str) -> None:
    conn.execute(
        "MERGE (n:Class {full_name: $full_name}) SET n.name = $name, n.kind = $kind",
        {"full_name": full_name, "name": name, "kind": kind},
    )


def upsert_method(
    conn: GraphConnection,
    full_name: str,
    name: str,
    signature: str,
    is_abstract: bool,
    is_static: bool,
) -> None:
    conn.execute(
        "MERGE (n:Method {full_name: $full_name}) "
        "SET n.name = $name, n.signature = $sig, n.is_abstract = $is_abstract, n.is_static = $is_static",
        {"full_name": full_name, "name": name, "sig": signature, "is_abstract": is_abstract, "is_static": is_static},
    )


def upsert_property(conn: GraphConnection, full_name: str, name: str, type_name: str) -> None:
    conn.execute(
        "MERGE (n:Property {full_name: $full_name}) SET n.name = $name, n.type_name = $type_name",
        {"full_name": full_name, "name": name, "type_name": type_name},
    )


def upsert_field(conn: GraphConnection, full_name: str, name: str, type_name: str) -> None:
    conn.execute(
        "MERGE (n:Field {full_name: $full_name}) SET n.name = $name, n.type_name = $type_name",
        {"full_name": full_name, "name": name, "type_name": type_name},
    )


def delete_file_nodes(conn: GraphConnection, file_path: str) -> None:
    """Delete all nodes that originated from the given file, and their edges."""
    conn.execute(
        "MATCH (f:File {path: $path})-[:CONTAINS*]->(n) DETACH DELETE n",
        {"path": file_path},
    )
    conn.execute(
        "MATCH (f:File {path: $path}) DETACH DELETE f",
        {"path": file_path},
    )


def set_summary(conn: GraphConnection, full_name: str, content: str) -> None:
    conn.execute(
        "MATCH (n {full_name: $full_name}) "
        "SET n:Summarized, n.summary = $content, n.summary_updated_at = $ts",
        {"full_name": full_name, "content": content, "ts": _now()},
    )


def remove_summary(conn: GraphConnection, full_name: str) -> None:
    conn.execute(
        "MATCH (n:Summarized {full_name: $full_name}) "
        "REMOVE n:Summarized REMOVE n.summary REMOVE n.summary_updated_at",
        {"full_name": full_name},
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/graph/test_nodes.py -v
```

Expected: 6 PASSED

**Step 5: Commit**

```bash
git add src/synapse/graph/nodes.py tests/unit/graph/test_nodes.py
git commit -m "feat: add graph node upsert and summary operations"
```

---

## Task 6: Graph Edge Upserts

**Files:**
- Create: `src/synapse/graph/edges.py`
- Create: `tests/unit/graph/test_edges.py`

**Step 1: Write the failing tests**

```python
# tests/unit/graph/test_edges.py
from unittest.mock import MagicMock
from synapse.graph.edges import (
    upsert_contains, upsert_calls, upsert_inherits,
    upsert_implements, upsert_overrides, upsert_references,
)


def _conn() -> MagicMock:
    return MagicMock()


def test_upsert_contains_uses_path_for_file_source() -> None:
    conn = _conn()
    upsert_contains(conn, from_path="/proj/Foo.cs", to_full_name="MyNs.MyClass")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "CONTAINS" in cypher
    assert params["from_id"] == "/proj/Foo.cs"


def test_upsert_calls_uses_full_names() -> None:
    conn = _conn()
    upsert_calls(conn, "MyNs.A.Do()", "MyNs.B.Run()")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "CALLS" in cypher
    assert params["caller"] == "MyNs.A.Do()"
    assert params["callee"] == "MyNs.B.Run()"


def test_upsert_implements_creates_edge() -> None:
    conn = _conn()
    upsert_implements(conn, "MyNs.ConcreteClass", "MyNs.IService")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "IMPLEMENTS" in cypher


def test_upsert_inherits_creates_edge() -> None:
    conn = _conn()
    upsert_inherits(conn, "MyNs.Child", "MyNs.Base")
    cypher = conn.execute.call_args[0][0]
    assert "INHERITS" in cypher


def test_upsert_overrides_creates_edge() -> None:
    conn = _conn()
    upsert_overrides(conn, "MyNs.Child.Run()", "MyNs.Base.Run()")
    cypher = conn.execute.call_args[0][0]
    assert "OVERRIDES" in cypher


def test_upsert_references_creates_edge() -> None:
    conn = _conn()
    upsert_references(conn, "MyNs.A.DoWork()", "MyNs.SomeType")
    cypher = conn.execute.call_args[0][0]
    assert "REFERENCES" in cypher
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/graph/test_edges.py -v
```

Expected: `ImportError`

**Step 3: Write the implementation**

```python
# src/synapse/graph/edges.py
from synapse.graph.connection import GraphConnection


def upsert_contains(conn: GraphConnection, from_path: str, to_full_name: str) -> None:
    """Create CONTAINS edge. from_path is a file or directory path; to_full_name is any symbol."""
    conn.execute(
        "MATCH (src {path: $from_id}), (dst {full_name: $to_id}) "
        "MERGE (src)-[:CONTAINS]->(dst)",
        {"from_id": from_path, "to_id": to_full_name},
    )


def upsert_contains_symbol(conn: GraphConnection, from_full_name: str, to_full_name: str) -> None:
    """Create CONTAINS edge between two symbols (e.g. Class → Method)."""
    conn.execute(
        "MATCH (src {full_name: $from_id}), (dst {full_name: $to_id}) "
        "MERGE (src)-[:CONTAINS]->(dst)",
        {"from_id": from_full_name, "to_id": to_full_name},
    )


def upsert_calls(conn: GraphConnection, caller_full_name: str, callee_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Method {full_name: $caller}), (dst:Method {full_name: $callee}) "
        "MERGE (src)-[:CALLS]->(dst)",
        {"caller": caller_full_name, "callee": callee_full_name},
    )


def upsert_inherits(conn: GraphConnection, child_full_name: str, parent_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Class {full_name: $child}), (dst:Class {full_name: $parent}) "
        "MERGE (src)-[:INHERITS]->(dst)",
        {"child": child_full_name, "parent": parent_full_name},
    )


def upsert_implements(conn: GraphConnection, class_full_name: str, interface_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Class {full_name: $cls}), (dst:Class {full_name: $iface}) "
        "MERGE (src)-[:IMPLEMENTS]->(dst)",
        {"cls": class_full_name, "iface": interface_full_name},
    )


def upsert_overrides(conn: GraphConnection, method_full_name: str, base_method_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Method {full_name: $method}), (dst:Method {full_name: $base}) "
        "MERGE (src)-[:OVERRIDES]->(dst)",
        {"method": method_full_name, "base": base_method_full_name},
    )


def upsert_references(conn: GraphConnection, from_full_name: str, type_full_name: str) -> None:
    conn.execute(
        "MATCH (src {full_name: $from_id}), (dst:Class {full_name: $to_id}) "
        "MERGE (src)-[:REFERENCES]->(dst)",
        {"from_id": from_full_name, "to_id": type_full_name},
    )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/graph/test_edges.py -v
```

Expected: 6 PASSED

**Step 5: Commit**

```bash
git add src/synapse/graph/edges.py tests/unit/graph/test_edges.py
git commit -m "feat: add graph edge upsert operations for all relationship types"
```

---

## Task 7: Graph Queries

**Files:**
- Create: `src/synapse/graph/queries.py`
- Create: `tests/unit/graph/test_queries.py`

**Step 1: Write the failing tests**

```python
# tests/unit/graph/test_queries.py
from unittest.mock import MagicMock
from synapse.graph.queries import (
    get_symbol, find_implementations, find_callers, find_callees,
    get_hierarchy, search_symbols, get_summary, list_summarized,
    list_projects, get_index_status,
)


def _conn(return_value: list) -> MagicMock:
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_get_symbol_returns_none_when_not_found() -> None:
    conn = _conn([])
    result = get_symbol(conn, "MyNs.MyClass")
    assert result is None


def test_get_symbol_returns_first_row() -> None:
    conn = _conn([[{"full_name": "MyNs.MyClass", "kind": "class"}]])
    result = get_symbol(conn, "MyNs.MyClass")
    assert result == {"full_name": "MyNs.MyClass", "kind": "class"}


def test_find_implementations_returns_list() -> None:
    conn = _conn([[{"full_name": "MyNs.Impl"}], [{"full_name": "MyNs.Impl2"}]])
    results = find_implementations(conn, "MyNs.IService")
    assert len(results) == 2


def test_find_callers_passes_full_name() -> None:
    conn = _conn([])
    find_callers(conn, "MyNs.A.Run()")
    cypher, params = conn.query.call_args[0][0], conn.query.call_args[0][1]
    assert "CALLS" in cypher
    assert params["full_name"] == "MyNs.A.Run()"


def test_search_symbols_with_kind_filter() -> None:
    conn = _conn([])
    search_symbols(conn, "Service", kind="Class")
    cypher, params = conn.query.call_args[0][0], conn.query.call_args[0][1]
    assert "Class" in cypher
    assert params["query"] in ("*Service*", "Service")


def test_list_projects_queries_repository_nodes() -> None:
    conn = _conn([])
    list_projects(conn)
    cypher = conn.query.call_args[0][0]
    assert "Repository" in cypher
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/graph/test_queries.py -v
```

Expected: `ImportError`

**Step 3: Write the implementation**

```python
# src/synapse/graph/queries.py
from synapse.graph.connection import GraphConnection


def get_symbol(conn: GraphConnection, full_name: str) -> dict | None:
    rows = conn.query(
        "MATCH (n {full_name: $full_name}) RETURN n",
        {"full_name": full_name},
    )
    return rows[0][0] if rows else None


def find_implementations(conn: GraphConnection, interface_full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (c:Class)-[:IMPLEMENTS]->(i:Class {full_name: $full_name}) RETURN c",
        {"full_name": interface_full_name},
    )
    return [r[0] for r in rows]


def find_callers(conn: GraphConnection, method_full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (caller:Method)-[:CALLS]->(m:Method {full_name: $full_name}) RETURN caller",
        {"full_name": method_full_name},
    )
    return [r[0] for r in rows]


def find_callees(conn: GraphConnection, method_full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (m:Method {full_name: $full_name})-[:CALLS]->(callee:Method) RETURN callee",
        {"full_name": method_full_name},
    )
    return [r[0] for r in rows]


def get_hierarchy(conn: GraphConnection, class_full_name: str) -> dict:
    parents = conn.query(
        "MATCH (c:Class {full_name: $full_name})-[:INHERITS*]->(p:Class) RETURN p",
        {"full_name": class_full_name},
    )
    children = conn.query(
        "MATCH (c:Class)-[:INHERITS*]->(p:Class {full_name: $full_name}) RETURN c",
        {"full_name": class_full_name},
    )
    return {"parents": [r[0] for r in parents], "children": [r[0] for r in children]}


def search_symbols(conn: GraphConnection, query: str, kind: str | None = None) -> list[dict]:
    pattern = f"*{query}*"
    if kind:
        rows = conn.query(
            f"MATCH (n:{kind}) WHERE n.name CONTAINS $query RETURN n",
            {"query": query},
        )
    else:
        rows = conn.query(
            "MATCH (n) WHERE n.name CONTAINS $query RETURN n",
            {"query": query},
        )
    return [r[0] for r in rows]


def get_summary(conn: GraphConnection, full_name: str) -> str | None:
    rows = conn.query(
        "MATCH (n:Summarized {full_name: $full_name}) RETURN n.summary",
        {"full_name": full_name},
    )
    return rows[0][0] if rows else None


def list_summarized(conn: GraphConnection, project_path: str | None = None) -> list[dict]:
    if project_path:
        rows = conn.query(
            "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n:Summarized) RETURN n",
            {"path": project_path},
        )
    else:
        rows = conn.query("MATCH (n:Summarized) RETURN n")
    return [r[0] for r in rows]


def list_projects(conn: GraphConnection) -> list[dict]:
    rows = conn.query("MATCH (r:Repository) RETURN r")
    return [r[0] for r in rows]


def get_index_status(conn: GraphConnection, project_path: str) -> dict | None:
    rows = conn.query(
        "MATCH (r:Repository {path: $path}) RETURN r",
        {"path": project_path},
    )
    if not rows:
        return None
    repo = rows[0][0]
    file_count = conn.query(
        "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(f:File) RETURN count(f)",
        {"path": project_path},
    )
    symbol_count = conn.query(
        "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n) WHERE NOT n:File AND NOT n:Directory RETURN count(n)",
        {"path": project_path},
    )
    return {
        "path": project_path,
        "last_indexed": repo.get("last_indexed"),
        "file_count": file_count[0][0] if file_count else 0,
        "symbol_count": symbol_count[0][0] if symbol_count else 0,
    }


def execute_readonly_query(conn: GraphConnection, cypher: str) -> list:
    """Execute a raw read-only Cypher query. Raises ValueError for mutating statements."""
    normalized = cypher.strip().upper()
    for mutating in ("CREATE", "MERGE", "DELETE", "SET", "REMOVE", "DROP"):
        if normalized.startswith(mutating) or f" {mutating} " in normalized:
            raise ValueError(f"Mutating Cypher statement not allowed: {mutating}")
    return conn.query(cypher)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/graph/test_queries.py -v
```

Expected: 6 PASSED

**Step 5: Commit**

```bash
git add src/synapse/graph/queries.py tests/unit/graph/test_queries.py
git commit -m "feat: add graph query operations for all MCP exploration tools"
```

---

## Task 8: LSP Adapter Interface and CSharp Implementation

**Files:**
- Create: `src/synapse/lsp/interface.py`
- Create: `src/synapse/lsp/csharp.py`
- Create: `tests/unit/lsp/test_csharp_adapter.py`

**Step 1: Write the failing tests**

```python
# tests/unit/lsp/test_csharp_adapter.py
from unittest.mock import MagicMock, patch
from synapse.lsp.interface import SymbolKind


def test_symbol_kind_values_cover_csharp_types() -> None:
    assert SymbolKind.CLASS in SymbolKind.__members__.values()
    assert SymbolKind.INTERFACE in SymbolKind.__members__.values()
    assert SymbolKind.METHOD in SymbolKind.__members__.values()
    assert SymbolKind.PROPERTY in SymbolKind.__members__.values()
    assert SymbolKind.FIELD in SymbolKind.__members__.values()
    assert SymbolKind.NAMESPACE in SymbolKind.__members__.values()


def test_csharp_adapter_implements_protocol() -> None:
    from synapse.lsp.interface import LSPAdapter
    from synapse.lsp.csharp import CSharpLSPAdapter
    # Protocol runtime check
    assert issubclass(CSharpLSPAdapter, LSPAdapter) or hasattr(CSharpLSPAdapter, "get_workspace_files")
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/lsp/ -v
```

Expected: `ImportError`

**Step 3: Write the interface**

```python
# src/synapse/lsp/interface.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class SymbolKind(str, Enum):
    NAMESPACE = "namespace"
    CLASS = "class"
    INTERFACE = "interface"
    ABSTRACT_CLASS = "abstract_class"
    ENUM = "enum"
    RECORD = "record"
    METHOD = "method"
    PROPERTY = "property"
    FIELD = "field"


@dataclass
class IndexSymbol:
    name: str
    full_name: str
    kind: SymbolKind
    file_path: str
    line: int
    signature: str = ""
    is_abstract: bool = False
    is_static: bool = False
    base_types: list[str] = field(default_factory=list)
    """Full names of base classes or implemented interfaces."""


@runtime_checkable
class LSPAdapter(Protocol):
    def get_workspace_files(self, root_path: str) -> list[str]:
        """Return absolute paths of all source files in the workspace."""
        ...

    def get_document_symbols(self, file_path: str) -> list[IndexSymbol]:
        """Return all symbols declared in the given file."""
        ...

    def find_method_calls(self, symbol: IndexSymbol) -> list[str]:
        """Return full_names of methods called by the given method symbol."""
        ...

    def find_overridden_method(self, symbol: IndexSymbol) -> str | None:
        """Return full_name of the base method that this method overrides, or None."""
        ...

    def shutdown(self) -> None:
        """Shut down the language server process."""
        ...
```

**Step 4: Write the CSharp adapter**

```python
# src/synapse/lsp/csharp.py
from __future__ import annotations

import logging
from pathlib import Path

from synapse.lsp.interface import IndexSymbol, LSPAdapter, SymbolKind

log = logging.getLogger(__name__)

# Maps LSP SymbolKind integers to our SymbolKind enum
# https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#symbolKind
_LSP_KIND_MAP: dict[int, SymbolKind] = {
    3: SymbolKind.NAMESPACE,
    5: SymbolKind.CLASS,
    11: SymbolKind.INTERFACE,
    10: SymbolKind.ENUM,
    6: SymbolKind.METHOD,
    7: SymbolKind.PROPERTY,
    8: SymbolKind.FIELD,
    9: SymbolKind.METHOD,  # Constructor → Method
    12: SymbolKind.METHOD,  # Function → Method
}


class CSharpLSPAdapter:
    """Wraps a SolidLanguageServer instance to provide the LSPAdapter interface for C#."""

    def __init__(self, language_server: object) -> None:
        self._ls = language_server

    @classmethod
    def create(cls, root_path: str) -> CSharpLSPAdapter:
        """Start the C# language server and return a ready adapter."""
        from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
        from solidlsp.ls_config import Language, LanguageServerConfig
        from solidlsp.settings import SolidLSPSettings

        config = LanguageServerConfig(
            language=Language.CSharp,
            project_root=root_path,
        )
        settings = SolidLSPSettings()
        ls = CSharpLanguageServer(config=config, settings=settings)
        ls.start()
        return cls(ls)

    def get_workspace_files(self, root_path: str) -> list[str]:
        files = []
        for path in Path(root_path).rglob("*.cs"):
            if ".git" not in path.parts and "bin" not in path.parts and "obj" not in path.parts:
                files.append(str(path))
        return files

    def get_document_symbols(self, file_path: str) -> list[IndexSymbol]:
        try:
            raw = self._ls.request_document_symbols(file_path)
            return [self._convert(s, file_path) for s in (raw or [])]
        except Exception:
            log.exception("Failed to get symbols for %s", file_path)
            return []

    def find_method_calls(self, symbol: IndexSymbol) -> list[str]:
        # Resolve via references: find all outgoing calls from this method's location
        try:
            refs = self._ls.find_references(symbol.file_path, symbol.line, 0, include_declaration=False)
            return [r.full_name for r in (refs or []) if hasattr(r, "full_name")]
        except Exception:
            log.exception("Failed to find calls for %s", symbol.full_name)
            return []

    def find_overridden_method(self, symbol: IndexSymbol) -> str | None:
        try:
            result = self._ls.go_to_definition(symbol.file_path, symbol.line, 0)
            if result and hasattr(result, "full_name"):
                return result.full_name
            return None
        except Exception:
            return None

    def shutdown(self) -> None:
        try:
            self._ls.shutdown()
        except Exception:
            log.warning("Language server did not shut down cleanly")

    def _convert(self, raw: object, file_path: str) -> IndexSymbol:
        kind_int = getattr(raw, "kind", 0)
        kind = _LSP_KIND_MAP.get(kind_int, SymbolKind.CLASS)
        return IndexSymbol(
            name=getattr(raw, "name", ""),
            full_name=getattr(raw, "full_name", "") or getattr(raw, "name", ""),
            kind=kind,
            file_path=file_path,
            line=getattr(raw, "line", 0),
            signature=getattr(raw, "signature", ""),
            is_abstract="abstract" in getattr(raw, "detail", "").lower(),
            is_static="static" in getattr(raw, "detail", "").lower(),
        )
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/lsp/ -v
```

Expected: 2 PASSED

**Step 6: Commit**

```bash
git add src/synapse/lsp/ tests/unit/lsp/
git commit -m "feat: add LSPAdapter protocol and CSharpLSPAdapter implementation"
```

---

## Task 9: Indexer — Structural Pass

Indexes files, namespaces, classes, methods, properties, and fields with CONTAINS edges.

**Files:**
- Create: `src/synapse/indexer/indexer.py`
- Create: `tests/unit/indexer/test_structural_pass.py`

**Step 1: Write the failing tests**

```python
# tests/unit/indexer/test_structural_pass.py
from unittest.mock import MagicMock, call
from synapse.indexer.indexer import Indexer
from synapse.lsp.interface import IndexSymbol, SymbolKind


def _make_symbol(name: str, kind: SymbolKind, file_path: str = "/proj/Foo.cs") -> IndexSymbol:
    return IndexSymbol(
        name=name,
        full_name=f"MyNs.{name}",
        kind=kind,
        file_path=file_path,
        line=10,
    )


def test_index_project_upserts_file_node() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = []

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("File" in c for c in calls)


def test_index_project_upserts_class_symbol() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = [
        _make_symbol("MyClass", SymbolKind.CLASS),
    ]
    lsp.find_method_calls.return_value = []
    lsp.find_overridden_method.return_value = None

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("MyClass" in c for c in calls)


def test_index_project_shuts_down_lsp() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = []

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    lsp.shutdown.assert_called_once()


def test_index_project_does_not_shut_down_lsp_in_watch_mode() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = []

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp", keep_lsp_running=True)

    lsp.shutdown.assert_not_called()
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/indexer/test_structural_pass.py -v
```

Expected: `ImportError`

**Step 3: Write the implementation**

```python
# src/synapse/indexer/indexer.py
from __future__ import annotations

import logging
import os

from synapse.graph.connection import GraphConnection
from synapse.graph.edges import (
    upsert_contains, upsert_contains_symbol, upsert_calls,
    upsert_inherits, upsert_implements, upsert_overrides,
)
from synapse.graph.nodes import upsert_file, upsert_directory, upsert_class, upsert_method, upsert_property, upsert_field, upsert_repository, upsert_namespace, delete_file_nodes
from synapse.lsp.interface import IndexSymbol, LSPAdapter, SymbolKind

log = logging.getLogger(__name__)


class Indexer:
    def __init__(self, conn: GraphConnection, lsp: LSPAdapter) -> None:
        self._conn = conn
        self._lsp = lsp

    def index_project(self, root_path: str, language: str, keep_lsp_running: bool = False) -> None:
        files = self._lsp.get_workspace_files(root_path)
        symbols_by_file: dict[str, list[IndexSymbol]] = {}

        # Structural pass
        for file_path in files:
            self._index_file_structure(file_path, root_path)
            symbols = self._lsp.get_document_symbols(file_path)
            symbols_by_file[file_path] = symbols

        # Relationship pass
        for file_path, symbols in symbols_by_file.items():
            self._index_file_relationships(symbols)

        upsert_repository(self._conn, root_path, language)

        if not keep_lsp_running:
            self._lsp.shutdown()

    def reindex_file(self, file_path: str, root_path: str) -> None:
        delete_file_nodes(self._conn, file_path)
        self._index_file_structure(file_path, root_path)
        symbols = self._lsp.get_document_symbols(file_path)
        self._index_file_relationships(symbols)

    def delete_file(self, file_path: str) -> None:
        delete_file_nodes(self._conn, file_path)

    def _index_file_structure(self, file_path: str, root_path: str) -> None:
        dir_path = os.path.dirname(file_path)
        dir_name = os.path.basename(dir_path)
        upsert_directory(self._conn, dir_path, dir_name)
        upsert_file(self._conn, file_path, os.path.basename(file_path), "csharp")
        upsert_contains(self._conn, from_path=dir_path, to_full_name=file_path)

        symbols = self._lsp.get_document_symbols(file_path)
        for symbol in symbols:
            self._upsert_symbol(symbol)
            upsert_contains(self._conn, from_path=file_path, to_full_name=symbol.full_name)

    def _upsert_symbol(self, symbol: IndexSymbol) -> None:
        match symbol.kind:
            case SymbolKind.NAMESPACE:
                upsert_namespace(self._conn, symbol.full_name, symbol.name)
            case SymbolKind.CLASS | SymbolKind.INTERFACE | SymbolKind.ABSTRACT_CLASS | SymbolKind.ENUM | SymbolKind.RECORD:
                upsert_class(self._conn, symbol.full_name, symbol.name, symbol.kind.value)
            case SymbolKind.METHOD:
                upsert_method(self._conn, symbol.full_name, symbol.name, symbol.signature, symbol.is_abstract, symbol.is_static)
            case SymbolKind.PROPERTY:
                upsert_property(self._conn, symbol.full_name, symbol.name, "")
            case SymbolKind.FIELD:
                upsert_field(self._conn, symbol.full_name, symbol.name, "")
            case _:
                log.debug("Skipping symbol of unhandled kind: %s", symbol.kind)

    def _index_file_relationships(self, symbols: list[IndexSymbol]) -> None:
        for symbol in symbols:
            # Base types (INHERITS / IMPLEMENTS)
            for base_type in symbol.base_types:
                if symbol.kind == SymbolKind.INTERFACE:
                    upsert_inherits(self._conn, symbol.full_name, base_type)
                else:
                    upsert_implements(self._conn, symbol.full_name, base_type)

            # Method calls (CALLS)
            if symbol.kind == SymbolKind.METHOD:
                for callee_full_name in self._lsp.find_method_calls(symbol):
                    upsert_calls(self._conn, symbol.full_name, callee_full_name)

                # Method overrides (OVERRIDES)
                overridden = self._lsp.find_overridden_method(symbol)
                if overridden:
                    upsert_overrides(self._conn, symbol.full_name, overridden)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/indexer/test_structural_pass.py -v
```

Expected: 4 PASSED

**Step 5: Commit**

```bash
git add src/synapse/indexer/ tests/unit/indexer/
git commit -m "feat: add Indexer with structural and relationship passes"
```

---

## Task 10: File Watcher

**Files:**
- Create: `src/synapse/watcher/watcher.py`
- Create: `tests/unit/watcher/test_watcher.py`

**Step 1: Write the failing tests**

```python
# tests/unit/watcher/test_watcher.py
import time
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from synapse.watcher.watcher import FileWatcher


@pytest.mark.timeout(5)
def test_watcher_calls_on_change_for_cs_file() -> None:
    on_change = MagicMock()
    on_delete = MagicMock()

    with tempfile.TemporaryDirectory() as tmpdir:
        watcher = FileWatcher(
            root_path=tmpdir,
            on_change=on_change,
            on_delete=on_delete,
            debounce_seconds=0.05,
        )
        watcher.start()
        try:
            test_file = Path(tmpdir) / "Test.cs"
            test_file.write_text("// hello")
            time.sleep(0.3)
            assert on_change.called
            args = on_change.call_args[0]
            assert args[0].endswith(".cs")
        finally:
            watcher.stop()


@pytest.mark.timeout(5)
def test_watcher_ignores_non_cs_files() -> None:
    on_change = MagicMock()
    on_delete = MagicMock()

    with tempfile.TemporaryDirectory() as tmpdir:
        watcher = FileWatcher(
            root_path=tmpdir,
            on_change=on_change,
            on_delete=on_delete,
            debounce_seconds=0.05,
        )
        watcher.start()
        try:
            (Path(tmpdir) / "notes.txt").write_text("ignore me")
            time.sleep(0.3)
            on_change.assert_not_called()
        finally:
            watcher.stop()


@pytest.mark.timeout(5)
def test_watcher_stop_joins_observer_thread() -> None:
    watcher = FileWatcher(
        root_path=tempfile.gettempdir(),
        on_change=MagicMock(),
        on_delete=MagicMock(),
        debounce_seconds=0.05,
    )
    watcher.start()
    watcher.stop()
    assert not watcher.is_running()
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/watcher/ -v
```

Expected: `ImportError`

**Step 3: Write the implementation**

```python
# src/synapse/watcher/watcher.py
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

log = logging.getLogger(__name__)

_WATCHED_EXTENSIONS = {".cs"}


class FileWatcher:
    """Watches a directory for C# file changes and calls back on modify/delete."""

    def __init__(
        self,
        root_path: str,
        on_change: Callable[[str], None],
        on_delete: Callable[[str], None],
        debounce_seconds: float = 0.5,
    ) -> None:
        self._root_path = root_path
        self._on_change = on_change
        self._on_delete = on_delete
        self._debounce_seconds = debounce_seconds
        self._observer = Observer()
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def start(self) -> None:
        handler = _ChangeHandler(self._on_change, self._on_delete, self._debounce_seconds, self._debounce_timers, self._lock)
        self._observer.schedule(handler, self._root_path, recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()
        with self._lock:
            for timer in self._debounce_timers.values():
                timer.cancel()

    def is_running(self) -> bool:
        return self._observer.is_alive()


class _ChangeHandler(FileSystemEventHandler):
    def __init__(
        self,
        on_change: Callable[[str], None],
        on_delete: Callable[[str], None],
        debounce_seconds: float,
        timers: dict[str, threading.Timer],
        lock: threading.Lock,
    ) -> None:
        self._on_change = on_change
        self._on_delete = on_delete
        self._debounce_seconds = debounce_seconds
        self._timers = timers
        self._lock = lock

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory and Path(event.src_path).suffix in _WATCHED_EXTENSIONS:
            self._debounce(event.src_path, self._on_change)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory and Path(event.src_path).suffix in _WATCHED_EXTENSIONS:
            self._debounce(event.src_path, self._on_change)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory and Path(event.src_path).suffix in _WATCHED_EXTENSIONS:
            self._debounce(event.src_path, self._on_delete)

    def _debounce(self, path: str, callback: Callable[[str], None]) -> None:
        with self._lock:
            if path in self._timers:
                self._timers[path].cancel()
            timer = threading.Timer(self._debounce_seconds, callback, args=[path])
            self._timers[path] = timer
            timer.start()
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/watcher/ -v
```

Expected: 3 PASSED

**Step 5: Commit**

```bash
git add src/synapse/watcher/ tests/unit/watcher/
git commit -m "feat: add FileWatcher with debounce for incremental re-indexing"
```

---

## Task 11: Core Service Layer

Provides a single entry point used by both MCP and CLI. Manages the FalkorDB connection, watcher lifecycle, and orchestrates indexer calls.

**Files:**
- Create: `src/synapse/service.py`
- Create: `tests/unit/test_service.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_service.py
from unittest.mock import MagicMock, patch
from synapse.service import SynapseService


def _service() -> SynapseService:
    conn = MagicMock()
    return SynapseService(conn=conn)


def test_set_summary_delegates_to_nodes() -> None:
    svc = _service()
    with patch("synapse.service.set_summary") as mock_set:
        svc.set_summary("MyNs.MyClass", "Auth handler")
        mock_set.assert_called_once_with(svc._conn, "MyNs.MyClass", "Auth handler")


def test_get_symbol_delegates_to_queries() -> None:
    svc = _service()
    with patch("synapse.service.get_symbol", return_value={"full_name": "X"}) as mock_get:
        result = svc.get_symbol("X")
        assert result == {"full_name": "X"}


def test_watch_project_registers_watcher() -> None:
    svc = _service()
    mock_watcher_cls = MagicMock()
    mock_watcher = MagicMock()
    mock_watcher_cls.return_value = mock_watcher

    with patch("synapse.service.FileWatcher", mock_watcher_cls):
        svc.watch_project("/proj", lsp_adapter=MagicMock())
        mock_watcher.start.assert_called_once()
        assert "/proj" in svc._watchers


def test_unwatch_project_stops_watcher() -> None:
    svc = _service()
    mock_watcher = MagicMock()
    svc._watchers["/proj"] = mock_watcher

    svc.unwatch_project("/proj")

    mock_watcher.stop.assert_called_once()
    assert "/proj" not in svc._watchers
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_service.py -v
```

Expected: `ImportError`

**Step 3: Write the implementation**

```python
# src/synapse/service.py
from __future__ import annotations

import logging

from synapse.graph.connection import GraphConnection
from synapse.graph.nodes import set_summary, remove_summary
from synapse.graph.queries import (
    get_symbol, find_implementations, find_callers, find_callees,
    get_hierarchy, search_symbols, get_summary, list_summarized,
    list_projects, get_index_status, execute_readonly_query,
)
from synapse.indexer.indexer import Indexer
from synapse.lsp.csharp import CSharpLSPAdapter
from synapse.lsp.interface import LSPAdapter
from synapse.watcher.watcher import FileWatcher

log = logging.getLogger(__name__)


class SynapseService:
    def __init__(self, conn: GraphConnection) -> None:
        self._conn = conn
        self._watchers: dict[str, FileWatcher] = {}

    # --- Indexing ---

    def index_project(self, path: str, language: str = "csharp") -> None:
        lsp = CSharpLSPAdapter.create(path)
        indexer = Indexer(self._conn, lsp)
        indexer.index_project(path, language)

    def delete_project(self, path: str) -> None:
        self._conn.execute(
            "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n) DETACH DELETE n",
            {"path": path},
        )
        self._conn.execute("MATCH (r:Repository {path: $path}) DETACH DELETE r", {"path": path})

    def watch_project(self, path: str, lsp_adapter: LSPAdapter | None = None) -> None:
        if path in self._watchers:
            return
        lsp = lsp_adapter or CSharpLSPAdapter.create(path)
        indexer = Indexer(self._conn, lsp)
        indexer.index_project(path, "csharp", keep_lsp_running=True)

        def on_change(file_path: str) -> None:
            log.info("Re-indexing changed file: %s", file_path)
            indexer.reindex_file(file_path, path)

        def on_delete(file_path: str) -> None:
            log.info("Removing deleted file: %s", file_path)
            indexer.delete_file(file_path)

        watcher = FileWatcher(root_path=path, on_change=on_change, on_delete=on_delete)
        watcher.start()
        self._watchers[path] = watcher

    def unwatch_project(self, path: str) -> None:
        watcher = self._watchers.pop(path, None)
        if watcher:
            watcher.stop()

    # --- Queries ---

    def get_symbol(self, full_name: str) -> dict | None:
        return get_symbol(self._conn, full_name)

    def find_implementations(self, interface_name: str) -> list[dict]:
        return find_implementations(self._conn, interface_name)

    def find_callers(self, method_full_name: str) -> list[dict]:
        return find_callers(self._conn, method_full_name)

    def find_callees(self, method_full_name: str) -> list[dict]:
        return find_callees(self._conn, method_full_name)

    def get_hierarchy(self, class_name: str) -> dict:
        return get_hierarchy(self._conn, class_name)

    def search_symbols(self, query: str, kind: str | None = None) -> list[dict]:
        return search_symbols(self._conn, query, kind)

    def list_projects(self) -> list[dict]:
        return list_projects(self._conn)

    def get_index_status(self, path: str) -> dict | None:
        return get_index_status(self._conn, path)

    def execute_query(self, cypher: str) -> list:
        return execute_readonly_query(self._conn, cypher)

    # --- Summaries ---

    def set_summary(self, full_name: str, content: str) -> None:
        set_summary(self._conn, full_name, content)

    def get_summary(self, full_name: str) -> str | None:
        return get_summary(self._conn, full_name)

    def list_summarized(self, project_path: str | None = None) -> list[dict]:
        return list_summarized(self._conn, project_path)

    def remove_summary(self, full_name: str) -> None:
        remove_summary(self._conn, full_name)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_service.py -v
```

Expected: 4 PASSED

**Step 5: Commit**

```bash
git add src/synapse/service.py tests/unit/test_service.py
git commit -m "feat: add SynapseService as shared entry point for MCP and CLI"
```

---

## Task 12: MCP Server

**Files:**
- Create: `src/synapse/mcp/server.py`
- Create: `src/synapse/mcp/tools.py`

**Step 1: Write the implementation**

No unit tests for MCP tool registration (testing the MCP framework itself is out of scope). Instead, ensure tools call through to the service layer correctly — covered by service layer tests above.

```python
# src/synapse/mcp/tools.py
from __future__ import annotations

from synapse.service import SynapseService


def register_tools(mcp: object, service: SynapseService) -> None:
    """Register all MCP tools on the given MCP server instance."""

    @mcp.tool()
    def index_project(path: str, language: str = "csharp") -> str:
        service.index_project(path, language)
        return f"Indexed {path}"

    @mcp.tool()
    def list_projects() -> list[dict]:
        return service.list_projects()

    @mcp.tool()
    def delete_project(path: str) -> str:
        service.delete_project(path)
        return f"Deleted {path}"

    @mcp.tool()
    def get_index_status(path: str) -> dict | None:
        return service.get_index_status(path)

    @mcp.tool()
    def get_symbol(full_name: str) -> dict | None:
        return service.get_symbol(full_name)

    @mcp.tool()
    def find_implementations(interface_name: str) -> list[dict]:
        return service.find_implementations(interface_name)

    @mcp.tool()
    def find_callers(method_full_name: str) -> list[dict]:
        return service.find_callers(method_full_name)

    @mcp.tool()
    def find_callees(method_full_name: str) -> list[dict]:
        return service.find_callees(method_full_name)

    @mcp.tool()
    def get_hierarchy(class_name: str) -> dict:
        return service.get_hierarchy(class_name)

    @mcp.tool()
    def search_symbols(query: str, kind: str | None = None) -> list[dict]:
        return service.search_symbols(query, kind)

    @mcp.tool()
    def set_summary(full_name: str, content: str) -> str:
        service.set_summary(full_name, content)
        return f"Summary saved for {full_name}"

    @mcp.tool()
    def get_summary(full_name: str) -> str | None:
        return service.get_summary(full_name)

    @mcp.tool()
    def list_summarized(project_path: str | None = None) -> list[dict]:
        return service.list_summarized(project_path)

    @mcp.tool()
    def execute_query(cypher: str) -> list:
        return service.execute_query(cypher)

    @mcp.tool()
    def watch_project(path: str) -> str:
        service.watch_project(path)
        return f"Watching {path}"

    @mcp.tool()
    def unwatch_project(path: str) -> str:
        service.unwatch_project(path)
        return f"Stopped watching {path}"
```

```python
# src/synapse/mcp/server.py
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server

from synapse.graph.connection import GraphConnection
from synapse.graph.schema import ensure_schema
from synapse.mcp.tools import register_tools
from synapse.service import SynapseService

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    conn = GraphConnection.create()
    ensure_schema(conn)
    service = SynapseService(conn)

    mcp = Server("synapse")
    register_tools(mcp, service)

    import asyncio
    asyncio.run(stdio_server(mcp))
```

**Step 2: Verify server starts without error**

```bash
python -c "from synapse.mcp.server import main; print('MCP server imports OK')"
```

Expected: `MCP server imports OK`

**Step 3: Commit**

```bash
git add src/synapse/mcp/
git commit -m "feat: add MCP server with all tool registrations"
```

---

## Task 13: CLI

**Files:**
- Create: `src/synapse/cli/app.py`
- Modify: `src/synapse/cli/__init__.py`

**Step 1: Write the implementation**

```python
# src/synapse/cli/app.py
from __future__ import annotations

from typing import Annotated, Optional

import typer

from synapse.graph.connection import GraphConnection
from synapse.graph.schema import ensure_schema
from synapse.service import SynapseService

app = typer.Typer(name="synapse", help="LSP-powered codebase graph tool")
summary_app = typer.Typer(name="summary")
app.add_typer(summary_app, name="summary")

_svc: SynapseService | None = None


def _get_service() -> SynapseService:
    global _svc
    if _svc is None:
        conn = GraphConnection.create()
        ensure_schema(conn)
        _svc = SynapseService(conn)
    return _svc


@app.command()
def index(path: str, language: str = "csharp") -> None:
    """Index a project into the graph."""
    _get_service().index_project(path, language)
    typer.echo(f"Indexed {path}")


@app.command()
def watch(path: str) -> None:
    """Watch a project for changes and keep the graph updated."""
    _get_service().watch_project(path)
    typer.echo(f"Watching {path}. Press Ctrl+C to stop.")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _get_service().unwatch_project(path)


@app.command()
def delete(path: str) -> None:
    """Remove a project from the graph."""
    _get_service().delete_project(path)
    typer.echo(f"Deleted {path}")


@app.command()
def status(path: Optional[str] = None) -> None:
    """Show index status for a project or all projects."""
    svc = _get_service()
    if path:
        result = svc.get_index_status(path)
        typer.echo(result or "Not indexed")
    else:
        for proj in svc.list_projects():
            typer.echo(proj)


@app.command()
def symbol(full_name: str) -> None:
    """Get a symbol's node and relationships."""
    result = _get_service().get_symbol(full_name)
    typer.echo(result or "Not found")


@app.command()
def callers(method_full_name: str) -> None:
    """Find all methods that call a given method."""
    for item in _get_service().find_callers(method_full_name):
        typer.echo(item)


@app.command()
def callees(method_full_name: str) -> None:
    """Find all methods called by a given method."""
    for item in _get_service().find_callees(method_full_name):
        typer.echo(item)


@app.command()
def implementations(interface_name: str) -> None:
    """Find all concrete implementations of an interface."""
    for item in _get_service().find_implementations(interface_name):
        typer.echo(item)


@app.command()
def hierarchy(class_name: str) -> None:
    """Show the full inheritance chain for a class."""
    result = _get_service().get_hierarchy(class_name)
    typer.echo(result)


@app.command()
def search(query: str, kind: Optional[str] = None) -> None:
    """Search symbols by name."""
    for item in _get_service().search_symbols(query, kind):
        typer.echo(item)


@app.command()
def query(cypher: str) -> None:
    """Execute a raw read-only Cypher query."""
    for row in _get_service().execute_query(cypher):
        typer.echo(row)


@summary_app.command("get")
def summary_get(full_name: str) -> None:
    """Get the summary for a symbol."""
    result = _get_service().get_summary(full_name)
    typer.echo(result or "No summary")


@summary_app.command("set")
def summary_set(full_name: str, content: str) -> None:
    """Set the summary for a symbol."""
    _get_service().set_summary(full_name, content)
    typer.echo(f"Summary saved for {full_name}")


@summary_app.command("list")
def summary_list(project: Optional[str] = None) -> None:
    """List all summarized symbols."""
    for item in _get_service().list_summarized(project):
        typer.echo(item)
```

```python
# src/synapse/cli/__init__.py
from synapse.cli.app import app
```

**Step 2: Verify CLI help works**

```bash
python -m synapse.cli.app --help
```

Expected: Shows list of commands without errors.

**Step 3: Commit**

```bash
git add src/synapse/cli/
git commit -m "feat: add Typer CLI for all Synapse operations"
```

---

## Task 14: Integration Test — Index C# Project

**Files:**
- Create: `tests/integration/test_index_project.py`

**Prerequisites:** FalkorDB running locally. Start with:
```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb:latest
```

**Step 1: Write the integration test**

```python
# tests/integration/test_index_project.py
"""
Integration tests against a C# project.
Requires FalkorDB running on localhost:6379.
Run with: pytest tests/integration/ -v -m integration
"""

import pytest
from synapse.graph.connection import GraphConnection
from synapse.graph.schema import ensure_schema
from synapse.service import SynapseService

CSHARP_BACKEND_PATH = "<path/to/csharp/project>"


@pytest.fixture(scope="module")
def service() -> SynapseService:
    conn = GraphConnection.create(graph_name="synapse_test")
    ensure_schema(conn)
    # Clear test graph
    conn.execute("MATCH (n) DETACH DELETE n")
    svc = SynapseService(conn)
    return svc


@pytest.mark.integration
@pytest.mark.timeout(120)
def test_index_project_completes(service: SynapseService) -> None:
    service.index_project(CSHARP_BACKEND_PATH, "csharp")
    status = service.get_index_status(CSHARP_BACKEND_PATH)
    assert status is not None
    assert status["file_count"] > 0
    assert status["symbol_count"] > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_can_query_classes_after_index(service: SynapseService) -> None:
    results = service.search_symbols("Controller", kind="Class")
    assert len(results) > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_set_and_get_summary(service: SynapseService) -> None:
    # Get any class to summarize
    classes = service.search_symbols("", kind="Class")
    assert classes, "No classes found — run test_index_project_completes first"
    full_name = classes[0]["full_name"]

    service.set_summary(full_name, "Test summary content")
    result = service.get_summary(full_name)
    assert result == "Test summary content"

    listed = service.list_summarized()
    names = [n.get("full_name") for n in listed]
    assert full_name in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_readonly_query(service: SynapseService) -> None:
    rows = service.execute_query("MATCH (n:Class) RETURN n.name LIMIT 5")
    assert isinstance(rows, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_mutating_query_raises(service: SynapseService) -> None:
    with pytest.raises(ValueError):
        service.execute_query("CREATE (n:Fake) RETURN n")
```

**Step 2: Add integration marker to pytest.ini**

```ini
[pytest]
timeout = 10
timeout_method = thread
testpaths = tests
markers =
    integration: marks tests as integration tests (require FalkorDB + C# LSP)
```

**Step 3: Run unit tests to verify nothing broken**

```bash
pytest tests/unit/ -v
```

Expected: all PASSED, no timeouts.

**Step 4: Run integration tests (requires FalkorDB + .NET)**

```bash
pytest tests/integration/ -v -m integration
```

Expected: all PASSED. If the C# LSP takes time to initialize, tests may use up to 120s.

**Step 5: Commit**

```bash
git add tests/integration/ pytest.ini
git commit -m "test: add integration tests for full C# project indexing"
```

---

## Run All Tests

```bash
pytest tests/unit/ -v
```

Expected: all unit tests pass within the 10s global timeout with no hanging.
