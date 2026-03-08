# Context Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add line ranges on symbol nodes, type reference edges, and a contextual retrieval tool (`get_context_for`) to make Synapse a context engine for LLM coding agents.

**Architecture:** Three phases executed sequentially. Phase 1 adds `end_line` to `IndexSymbol` and node upserts, plus a `get_symbol_source()` tool. Phase 2 refactors `CallIndexer` into a `SymbolResolver` coordinator that runs both call extraction and new type reference extraction in a single file walk. Phase 3 builds `get_context_for()` as pure query composition on top of Phases 1-2.

**Tech Stack:** Python 3.11+, FalkorDB (Cypher), tree-sitter + tree-sitter-c-sharp, solidlsp (LSP), MCP (FastMCP), Typer (CLI), pytest

**Design Doc:** `docs/plans/2026-03-08-context-features-design.md`

---

## Phase 1: Line Ranges & `get_symbol_source()`

### Task 1: Add `end_line` to `IndexSymbol`

**Files:**
- Modify: `src/synapse/lsp/interface.py:21-33`
- Test: `tests/unit/lsp/test_csharp_adapter.py`

**Step 1: Write the failing test**

Create a test that asserts `IndexSymbol` has an `end_line` field defaulting to 0.

```python
# In tests/unit/lsp/test_csharp_adapter.py (or a new test_interface.py if preferred)
from synapse.lsp.interface import IndexSymbol, SymbolKind

def test_index_symbol_has_end_line_default():
    sym = IndexSymbol(name="Foo", full_name="Ns.Foo", kind=SymbolKind.CLASS, file_path="/f.cs", line=0)
    assert sym.end_line == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/lsp/test_csharp_adapter.py::test_index_symbol_has_end_line_default -v`
Expected: FAIL with `AttributeError` or `TypeError`

**Step 3: Write minimal implementation**

Add `end_line: int = 0` to the `IndexSymbol` dataclass in `src/synapse/lsp/interface.py:26` (after `line: int`):

```python
@dataclass
class IndexSymbol:
    name: str
    full_name: str
    kind: SymbolKind
    file_path: str
    line: int
    end_line: int = 0
    signature: str = ""
    is_abstract: bool = False
    is_static: bool = False
    base_types: list[str] = field(default_factory=list)
    """Full names of base classes or implemented interfaces."""
    parent_full_name: str | None = None
    """full_name of the enclosing symbol, or None if top-level in the file."""
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/lsp/test_csharp_adapter.py::test_index_symbol_has_end_line_default -v`
Expected: PASS

**Step 5: Run full test suite to check for regressions**

Run: `pytest tests/unit/ -v`
Expected: All tests pass. Existing code that constructs `IndexSymbol` uses keyword args; `end_line=0` default means no breakage.

**Step 6: Commit**

```bash
git add src/synapse/lsp/interface.py tests/unit/lsp/test_csharp_adapter.py
git commit -m "feat: add end_line field to IndexSymbol"
```

---

### Task 2: Capture `end_line` from LSP in `CSharpLSPAdapter._convert()`

**Files:**
- Modify: `src/synapse/lsp/csharp.py:94-113`
- Test: `tests/unit/lsp/test_csharp_adapter.py`

**Step 1: Write the failing test**

```python
# In tests/unit/lsp/test_csharp_adapter.py
from synapse.lsp.csharp import CSharpLSPAdapter
from unittest.mock import MagicMock

def test_convert_captures_end_line():
    ls = MagicMock()
    adapter = CSharpLSPAdapter(ls)
    raw = {
        "name": "MyMethod",
        "kind": 6,  # Method
        "detail": "void MyMethod()",
        "location": {
            "range": {
                "start": {"line": 10, "character": 4},
                "end": {"line": 25, "character": 5},
            }
        },
    }
    sym = adapter._convert(raw, "/proj/Foo.cs", parent_full_name="MyNs.MyClass")
    assert sym.end_line == 25
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/lsp/test_csharp_adapter.py::test_convert_captures_end_line -v`
Expected: FAIL — `sym.end_line` is 0 (default)

**Step 3: Write minimal implementation**

In `src/synapse/lsp/csharp.py`, modify `_convert()` to also capture end line. Change line 101 area:

```python
def _convert(self, raw: dict, file_path: str, parent_full_name: str | None) -> IndexSymbol:
    kind_int = raw.get("kind", 0)
    kind = _LSP_KIND_MAP.get(kind_int)
    if kind is None:
        log.debug("Unmapped LSP SymbolKind %d for symbol %s, defaulting to CLASS", kind_int, raw.get("name", "?"))
        kind = SymbolKind.CLASS
    name = raw.get("name", "")
    range_obj = raw.get("location", {}).get("range", {})
    line = range_obj.get("start", {}).get("line", 0)
    end_line = range_obj.get("end", {}).get("line", 0)
    detail = raw.get("detail", "") or ""
    return IndexSymbol(
        name=name,
        full_name=build_full_name(raw),
        kind=kind,
        file_path=file_path,
        line=line,
        end_line=end_line,
        signature=detail,
        is_abstract="abstract" in detail.lower(),
        is_static="static" in detail.lower(),
        parent_full_name=parent_full_name,
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/lsp/test_csharp_adapter.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/synapse/lsp/csharp.py tests/unit/lsp/test_csharp_adapter.py
git commit -m "feat: capture end_line from LSP range in CSharpLSPAdapter"
```

---

### Task 3: Add `end_line` to node upsert functions

**Files:**
- Modify: `src/synapse/graph/nodes.py:34-75`
- Test: `tests/unit/graph/test_nodes.py`

**Step 1: Write failing tests**

```python
# In tests/unit/graph/test_nodes.py

def test_upsert_method_includes_end_line() -> None:
    conn = _conn()
    upsert_method(conn, "Ns.C.M()", "M", "void M()", is_abstract=False, is_static=False, line=5, end_line=15)
    _, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert params["end_line"] == 15


def test_upsert_class_includes_end_line() -> None:
    conn = _conn()
    upsert_class(conn, "Ns.C", "C", "class", end_line=50)
    _, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert params["end_line"] == 50


def test_upsert_interface_includes_end_line() -> None:
    conn = _conn()
    upsert_interface(conn, "Ns.I", "I", end_line=30)
    _, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert params["end_line"] == 30


def test_upsert_property_includes_end_line() -> None:
    conn = _conn()
    upsert_property(conn, "Ns.C.P", "P", "string", end_line=12)
    _, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert params["end_line"] == 12


def test_upsert_field_includes_end_line() -> None:
    conn = _conn()
    upsert_field(conn, "Ns.C._f", "_f", "int", end_line=8)
    _, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert params["end_line"] == 8
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/graph/test_nodes.py::test_upsert_method_includes_end_line tests/unit/graph/test_nodes.py::test_upsert_class_includes_end_line tests/unit/graph/test_nodes.py::test_upsert_interface_includes_end_line tests/unit/graph/test_nodes.py::test_upsert_property_includes_end_line tests/unit/graph/test_nodes.py::test_upsert_field_includes_end_line -v`
Expected: FAIL — `end_line` not an accepted parameter

**Step 3: Write minimal implementation**

Modify all five upsert functions in `src/synapse/graph/nodes.py` to accept and store `end_line`:

```python
def upsert_interface(conn: GraphConnection, full_name: str, name: str, end_line: int = 0) -> None:
    conn.execute(
        "MERGE (n:Interface {full_name: $full_name}) SET n.name = $name, n.end_line = $end_line",
        {"full_name": full_name, "name": name, "end_line": end_line},
    )


def upsert_class(conn: GraphConnection, full_name: str, name: str, kind: str, end_line: int = 0) -> None:
    conn.execute(
        "MERGE (n:Class {full_name: $full_name}) SET n.name = $name, n.kind = $kind, n.end_line = $end_line",
        {"full_name": full_name, "name": name, "kind": kind, "end_line": end_line},
    )


def upsert_method(
    conn: GraphConnection,
    full_name: str,
    name: str,
    signature: str,
    is_abstract: bool,
    is_static: bool,
    line: int | None = None,
    end_line: int = 0,
) -> None:
    conn.execute(
        "MERGE (n:Method {full_name: $full_name}) "
        "SET n.name = $name, n.signature = $sig, n.is_abstract = $is_abstract, n.is_static = $is_static, n.line = $line, n.end_line = $end_line",
        {"full_name": full_name, "name": name, "sig": signature, "is_abstract": is_abstract, "is_static": is_static, "line": line, "end_line": end_line},
    )


def upsert_property(conn: GraphConnection, full_name: str, name: str, type_name: str, end_line: int = 0) -> None:
    conn.execute(
        "MERGE (n:Property {full_name: $full_name}) SET n.name = $name, n.type_name = $type_name, n.end_line = $end_line",
        {"full_name": full_name, "name": name, "type_name": type_name, "end_line": end_line},
    )


def upsert_field(conn: GraphConnection, full_name: str, name: str, type_name: str, end_line: int = 0) -> None:
    conn.execute(
        "MERGE (n:Field {full_name: $full_name}) SET n.name = $name, n.type_name = $type_name, n.end_line = $end_line",
        {"full_name": full_name, "name": name, "type_name": type_name, "end_line": end_line},
    )
```

**Step 4: Run all tests to verify**

Run: `pytest tests/unit/ -v`
Expected: All pass. Existing callers that don't pass `end_line` use the default of 0.

**Step 5: Commit**

```bash
git add src/synapse/graph/nodes.py tests/unit/graph/test_nodes.py
git commit -m "feat: add end_line parameter to symbol upsert functions"
```

---

### Task 4: Pass `end_line` through the Indexer

**Files:**
- Modify: `src/synapse/indexer/indexer.py:134-149`
- Test: `tests/unit/indexer/test_structural_pass.py`

**Step 1: Write the failing test**

Read `tests/unit/indexer/test_structural_pass.py` first to understand the existing pattern, then add:

```python
def test_upsert_symbol_passes_end_line(mock_conn):
    """Verify that _upsert_symbol passes end_line from IndexSymbol to the node upsert."""
    lsp = MagicMock(spec=LSPAdapter)
    indexer = Indexer(mock_conn, lsp)
    sym = IndexSymbol(
        name="MyMethod", full_name="Ns.C.MyMethod", kind=SymbolKind.METHOD,
        file_path="/proj/F.cs", line=10, end_line=20, signature="void MyMethod()",
    )
    indexer._upsert_symbol(sym)
    _, params = mock_conn.execute.call_args[0]
    assert params["end_line"] == 20
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/indexer/test_structural_pass.py::test_upsert_symbol_passes_end_line -v`
Expected: FAIL — `end_line` not in params (current code doesn't pass it)

**Step 3: Write minimal implementation**

Modify `_upsert_symbol` in `src/synapse/indexer/indexer.py:134-149` to pass `end_line`:

```python
def _upsert_symbol(self, symbol: IndexSymbol) -> None:
    match symbol.kind:
        case SymbolKind.NAMESPACE:
            upsert_package(self._conn, symbol.full_name, symbol.name)
        case SymbolKind.INTERFACE:
            upsert_interface(self._conn, symbol.full_name, symbol.name, end_line=symbol.end_line)
        case SymbolKind.CLASS | SymbolKind.ABSTRACT_CLASS | SymbolKind.ENUM | SymbolKind.RECORD:
            upsert_class(self._conn, symbol.full_name, symbol.name, symbol.kind.value, end_line=symbol.end_line)
        case SymbolKind.METHOD:
            upsert_method(self._conn, symbol.full_name, symbol.name, symbol.signature, symbol.is_abstract, symbol.is_static, symbol.line, end_line=symbol.end_line)
        case SymbolKind.PROPERTY:
            upsert_property(self._conn, symbol.full_name, symbol.name, "", end_line=symbol.end_line)
        case SymbolKind.FIELD:
            upsert_field(self._conn, symbol.full_name, symbol.name, "", end_line=symbol.end_line)
        case _:
            log.debug("Skipping symbol of unhandled kind: %s", symbol.kind)
```

**Step 4: Run tests**

Run: `pytest tests/unit/ -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/synapse/indexer/indexer.py tests/unit/indexer/test_structural_pass.py
git commit -m "feat: pass end_line through Indexer to node upserts"
```

---

### Task 5: Add `get_symbol_source` query

**Files:**
- Modify: `src/synapse/graph/queries.py`
- Test: `tests/unit/graph/test_queries.py`

**Step 1: Write the failing test**

```python
# In tests/unit/graph/test_queries.py
from synapse.graph.queries import get_symbol_source_info

def test_get_symbol_source_info_returns_location() -> None:
    conn = _conn([["/proj/Foo.cs", 10, 25]])
    result = get_symbol_source_info(conn, "Ns.C.MyMethod")
    assert result == {"file_path": "/proj/Foo.cs", "line": 10, "end_line": 25}


def test_get_symbol_source_info_returns_none_when_not_found() -> None:
    conn = _conn([])
    result = get_symbol_source_info(conn, "Ns.Missing")
    assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/graph/test_queries.py::test_get_symbol_source_info_returns_location tests/unit/graph/test_queries.py::test_get_symbol_source_info_returns_none_when_not_found -v`
Expected: FAIL — `get_symbol_source_info` doesn't exist

**Step 3: Write minimal implementation**

Add to `src/synapse/graph/queries.py`:

```python
def get_symbol_source_info(conn: GraphConnection, full_name: str) -> dict | None:
    rows = conn.query(
        "MATCH (f:File)-[:CONTAINS*]->(n {full_name: $full_name}) "
        "RETURN f.path, n.line, n.end_line",
        {"full_name": full_name},
    )
    if not rows:
        return None
    return {"file_path": rows[0][0], "line": rows[0][1], "end_line": rows[0][2]}
```

**Step 4: Run tests**

Run: `pytest tests/unit/graph/test_queries.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/synapse/graph/queries.py tests/unit/graph/test_queries.py
git commit -m "feat: add get_symbol_source_info query"
```

---

### Task 6: Add `get_symbol_source` to service layer

**Files:**
- Modify: `src/synapse/service.py`
- Test: `tests/unit/test_service.py`

**Step 1: Read the existing test file**

Read `tests/unit/test_service.py` to understand the test pattern.

**Step 2: Write the failing test**

```python
def test_get_symbol_source_reads_file_and_returns_lines(tmp_path):
    """Service reads the file from disk using line range from the graph."""
    source_file = tmp_path / "Foo.cs"
    source_file.write_text("line0\nline1\nline2\nline3\nline4\nline5\n")

    conn = MagicMock()
    svc = SynapseService(conn)

    with patch("synapse.service.get_symbol_source_info") as mock_query:
        mock_query.return_value = {"file_path": str(source_file), "line": 1, "end_line": 3}
        result = svc.get_symbol_source("Ns.C.M")

    assert "line1" in result
    assert "line2" in result
    assert "line3" in result
    assert "line0" not in result


def test_get_symbol_source_returns_none_when_symbol_not_found():
    conn = MagicMock()
    svc = SynapseService(conn)

    with patch("synapse.service.get_symbol_source_info") as mock_query:
        mock_query.return_value = None
        result = svc.get_symbol_source("Ns.Missing")

    assert result is None


def test_get_symbol_source_returns_error_when_end_line_missing(tmp_path):
    """When end_line is 0, the symbol was indexed before line ranges were added."""
    conn = MagicMock()
    svc = SynapseService(conn)

    with patch("synapse.service.get_symbol_source_info") as mock_query:
        mock_query.return_value = {"file_path": str(tmp_path / "F.cs"), "line": 5, "end_line": 0}
        result = svc.get_symbol_source("Ns.C.M")

    assert result is not None
    assert "re-index" in result.lower()
```

**Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_service.py::test_get_symbol_source_reads_file_and_returns_lines tests/unit/test_service.py::test_get_symbol_source_returns_none_when_symbol_not_found tests/unit/test_service.py::test_get_symbol_source_returns_error_when_end_line_missing -v`
Expected: FAIL — method doesn't exist

**Step 4: Write minimal implementation**

Add to `src/synapse/service.py`:

1. Add `get_symbol_source_info` to the imports from `synapse.graph.queries`.
2. Add the method:

```python
def get_symbol_source(self, full_name: str, include_class_signature: bool = False) -> str | None:
    info = get_symbol_source_info(self._conn, full_name)
    if info is None:
        return None
    file_path = info["file_path"]
    line = info["line"]
    end_line = info["end_line"]
    if not end_line:
        return f"Symbol '{full_name}' was indexed without line ranges. Re-index the project to enable source retrieval."
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
    except OSError:
        return f"Source file not found: {file_path}"
    # Lines are 0-indexed in the graph, file lines are 0-indexed in the list
    source_lines = all_lines[line:end_line + 1]
    result = f"// {file_path}:{line + 1}\n{''.join(source_lines)}"
    if include_class_signature:
        parent = self._get_parent_signature(full_name)
        if parent:
            result = parent + "\n\n" + result
    return result

def _get_parent_signature(self, full_name: str) -> str | None:
    """Get the declaration line of the containing class/interface."""
    rows = self._conn.query(
        "MATCH (parent)-[:CONTAINS]->(n {full_name: $full_name}) "
        "WHERE parent:Class OR parent:Interface "
        "RETURN parent.full_name, parent.line, parent.end_line",
        {"full_name": full_name},
    )
    if not rows:
        return None
    parent_full_name = rows[0][0]
    parent_line = rows[0][1]
    if parent_line is None:
        return f"// Containing type: {parent_full_name}"
    parent_info = get_symbol_source_info(self._conn, parent_full_name)
    if not parent_info or not parent_info["file_path"]:
        return f"// Containing type: {parent_full_name}"
    try:
        with open(parent_info["file_path"], encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
        return f"// {parent_info['file_path']}:{parent_line + 1}\n{all_lines[parent_line].rstrip()}"
    except (OSError, IndexError):
        return f"// Containing type: {parent_full_name}"
```

**Step 5: Run tests**

Run: `pytest tests/unit/test_service.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add src/synapse/service.py tests/unit/test_service.py
git commit -m "feat: add get_symbol_source to service layer"
```

---

### Task 7: Add `get_symbol_source` MCP tool and CLI command

**Files:**
- Modify: `src/synapse/mcp/tools.py`
- Modify: `src/synapse/cli/app.py`

**Step 1: Add the MCP tool**

In `src/synapse/mcp/tools.py`, add after the `get_symbol` tool:

```python
@mcp.tool()
def get_symbol_source(full_name: str, include_class_signature: bool = False) -> str:
    result = service.get_symbol_source(full_name, include_class_signature)
    return result or f"Symbol not found: {full_name}"
```

**Step 2: Add the CLI command**

In `src/synapse/cli/app.py`, add:

```python
@app.command()
def source(full_name: str, include_class: bool = False) -> None:
    """Print the source code of a symbol."""
    result = _get_service().get_symbol_source(full_name, include_class_signature=include_class)
    typer.echo(result or "Not found")
```

**Step 3: Run full test suite**

Run: `pytest tests/unit/ -v`
Expected: All pass

**Step 4: Commit**

```bash
git add src/synapse/mcp/tools.py src/synapse/cli/app.py
git commit -m "feat: add get_symbol_source MCP tool and CLI command"
```

---

## Phase 2: SymbolResolver & Type Reference Edges

### Task 8: Add `upsert_references` edge function

**Files:**
- Modify: `src/synapse/graph/edges.py`
- Test: `tests/unit/graph/test_edges.py`

**Step 1: Write the failing test**

```python
# In tests/unit/graph/test_edges.py
from synapse.graph.edges import upsert_references

def test_upsert_references_creates_edge_with_kind():
    conn = MagicMock()
    upsert_references(conn, "Ns.C.M()", "Ns.UserDto", "parameter")
    cypher, params = conn.execute.call_args[0]
    assert "REFERENCES" in cypher
    assert params["source"] == "Ns.C.M()"
    assert params["target"] == "Ns.UserDto"
    assert params["kind"] == "parameter"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/graph/test_edges.py::test_upsert_references_creates_edge_with_kind -v`
Expected: FAIL — `upsert_references` doesn't exist

**Step 3: Write minimal implementation**

Add to `src/synapse/graph/edges.py`:

```python
def upsert_references(conn: GraphConnection, source_full_name: str, target_full_name: str, kind: str) -> None:
    conn.execute(
        "MATCH (src {full_name: $source}), (dst {full_name: $target}) "
        "WHERE dst:Class OR dst:Interface "
        "MERGE (src)-[r:REFERENCES {kind: $kind}]->(dst)",
        {"source": source_full_name, "target": target_full_name, "kind": kind},
    )
```

**Step 4: Run tests**

Run: `pytest tests/unit/graph/test_edges.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/synapse/graph/edges.py tests/unit/graph/test_edges.py
git commit -m "feat: add upsert_references edge function"
```

---

### Task 9: Add `find_type_references` and `find_dependencies` queries

**Files:**
- Modify: `src/synapse/graph/queries.py`
- Test: `tests/unit/graph/test_queries.py`

**Step 1: Write failing tests**

```python
# In tests/unit/graph/test_queries.py
from synapse.graph.queries import find_type_references, find_dependencies

def test_find_type_references_returns_referencing_symbols() -> None:
    conn = _conn([[{"full_name": "Ns.C.M()", "name": "M"}, "parameter"]])
    results = find_type_references(conn, "Ns.UserDto")
    assert len(results) == 1
    assert results[0]["symbol"]["full_name"] == "Ns.C.M()"
    assert results[0]["kind"] == "parameter"


def test_find_type_references_returns_empty_for_no_refs() -> None:
    conn = _conn([])
    results = find_type_references(conn, "Ns.Orphan")
    assert results == []


def test_find_dependencies_returns_referenced_types() -> None:
    conn = _conn([[{"full_name": "Ns.UserDto", "name": "UserDto"}, "return_type"]])
    results = find_dependencies(conn, "Ns.C.M()")
    assert len(results) == 1
    assert results[0]["type"]["full_name"] == "Ns.UserDto"
    assert results[0]["kind"] == "return_type"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/graph/test_queries.py::test_find_type_references_returns_referencing_symbols tests/unit/graph/test_queries.py::test_find_dependencies_returns_referenced_types -v`
Expected: FAIL — functions don't exist

**Step 3: Write minimal implementation**

Add to `src/synapse/graph/queries.py`:

```python
def find_type_references(conn: GraphConnection, full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (src)-[r:REFERENCES]->(t {full_name: $full_name}) RETURN src, r.kind",
        {"full_name": full_name},
    )
    return [{"symbol": row[0], "kind": row[1]} for row in rows]


def find_dependencies(conn: GraphConnection, full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (n {full_name: $full_name})-[r:REFERENCES]->(t) RETURN t, r.kind",
        {"full_name": full_name},
    )
    return [{"type": row[0], "kind": row[1]} for row in rows]
```

**Step 4: Run tests**

Run: `pytest tests/unit/graph/test_queries.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/synapse/graph/queries.py tests/unit/graph/test_queries.py
git commit -m "feat: add find_type_references and find_dependencies queries"
```

---

### Task 10: Build `TreeSitterTypeRefExtractor`

**Files:**
- Create: `src/synapse/indexer/type_ref_extractor.py`
- Create: `tests/unit/indexer/test_type_ref_extractor.py`

**Step 1: Write failing tests**

```python
# tests/unit/indexer/test_type_ref_extractor.py
import pytest
from synapse.indexer.type_ref_extractor import TreeSitterTypeRefExtractor


@pytest.fixture
def extractor():
    return TreeSitterTypeRefExtractor()


def test_extracts_method_return_type(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        public UserDto GetUser() {
            return null;
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.GetUser"}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    assert any(r.ref_kind == "return_type" and r.type_name == "UserDto" for r in results)


def test_extracts_method_parameter_type(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        public void Save(UserDto dto) {}
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.Save"}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    assert any(r.ref_kind == "parameter" and r.type_name == "UserDto" for r in results)


def test_extracts_property_type(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        public UserDto User { get; set; }
    }
}
"""
    # Properties need a class-level symbol map entry
    symbol_map = {}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    assert any(r.ref_kind == "property_type" and r.type_name == "UserDto" for r in results)


def test_extracts_field_type(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        private UserDto _user;
    }
}
"""
    symbol_map = {}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    assert any(r.ref_kind == "field_type" and r.type_name == "UserDto" for r in results)


def test_skips_primitive_types(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        public int GetCount() { return 0; }
        private string _name;
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.GetCount"}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    type_names = [r.type_name for r in results]
    assert "int" not in type_names
    assert "string" not in type_names


def test_returns_empty_for_empty_source(extractor):
    assert extractor.extract("/proj/Empty.cs", "", {}) == []
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/indexer/test_type_ref_extractor.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Write implementation**

Create `src/synapse/indexer/type_ref_extractor.py`:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

# C# built-in type keywords that should not produce REFERENCES edges
_PRIMITIVE_TYPES = frozenset({
    "bool", "byte", "sbyte", "char", "decimal", "double", "float",
    "int", "uint", "long", "ulong", "short", "ushort", "string",
    "object", "void", "nint", "nuint", "dynamic", "var",
})

_RETURN_TYPE_QUERY = """
(method_declaration
    type: (_) @return_type
    name: (identifier) @method_name
)
(constructor_declaration
    name: (identifier) @ctor_name
)
"""

_PARAM_QUERY = """
(parameter
    type: (_) @param_type
)
"""

_PROPERTY_QUERY = """
(property_declaration
    type: (_) @prop_type
    name: (identifier) @prop_name
)
"""

_FIELD_QUERY = """
(field_declaration
    type: (_) @field_type
)
"""


@dataclass
class TypeRef:
    owner_full_name: str
    type_name: str
    line: int
    col: int
    ref_kind: str  # "parameter", "return_type", "property_type", "field_type"


class TreeSitterTypeRefExtractor:
    def __init__(self) -> None:
        import tree_sitter_c_sharp
        from tree_sitter import Language, Parser, Query, QueryCursor

        self._language = Language(tree_sitter_c_sharp.language())
        self._parser = Parser(self._language)
        self._return_query = Query(self._language, _RETURN_TYPE_QUERY)
        self._param_query = Query(self._language, _PARAM_QUERY)
        self._property_query = Query(self._language, _PROPERTY_QUERY)
        self._field_query = Query(self._language, _FIELD_QUERY)
        self._QueryCursor = QueryCursor

    def extract(
        self,
        file_path: str,
        source: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> list[TypeRef]:
        if not source.strip():
            return []

        try:
            tree = self._parser.parse(bytes(source, "utf-8"))
        except Exception:
            log.warning("tree-sitter failed to parse %s", file_path)
            return []

        method_lines = sorted(
            (line, full_name)
            for (fp, line), full_name in symbol_map.items()
            if fp == file_path
        )

        results: list[TypeRef] = []
        self._extract_return_types(tree, file_path, method_lines, results)
        self._extract_param_types(tree, file_path, method_lines, results)
        self._extract_property_types(tree, file_path, source, results)
        self._extract_field_types(tree, file_path, source, results)
        return results

    def _extract_return_types(self, tree, file_path, method_lines, results):
        cursor = self._QueryCursor(self._return_query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            type_nodes = captures.get("return_type", [])
            for node in type_nodes:
                type_name = self._get_type_name(node)
                if type_name and type_name not in _PRIMITIVE_TYPES:
                    line_0 = node.start_point[0]
                    owner = self._find_enclosing_method(line_0, method_lines)
                    if owner:
                        results.append(TypeRef(
                            owner_full_name=owner, type_name=type_name,
                            line=node.start_point[0], col=node.start_point[1],
                            ref_kind="return_type",
                        ))

    def _extract_param_types(self, tree, file_path, method_lines, results):
        cursor = self._QueryCursor(self._param_query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            type_nodes = captures.get("param_type", [])
            for node in type_nodes:
                type_name = self._get_type_name(node)
                if type_name and type_name not in _PRIMITIVE_TYPES:
                    line_0 = node.start_point[0]
                    owner = self._find_enclosing_method(line_0, method_lines)
                    if owner:
                        results.append(TypeRef(
                            owner_full_name=owner, type_name=type_name,
                            line=node.start_point[0], col=node.start_point[1],
                            ref_kind="parameter",
                        ))

    def _extract_property_types(self, tree, file_path, source, results):
        cursor = self._QueryCursor(self._property_query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            type_nodes = captures.get("prop_type", [])
            name_nodes = captures.get("prop_name", [])
            for type_node, name_node in zip(type_nodes, name_nodes):
                type_name = self._get_type_name(type_node)
                prop_name = name_node.text.decode("utf-8") if isinstance(name_node.text, bytes) else name_node.text
                if type_name and type_name not in _PRIMITIVE_TYPES:
                    results.append(TypeRef(
                        owner_full_name=prop_name,  # Placeholder — resolved by SymbolResolver
                        type_name=type_name,
                        line=type_node.start_point[0], col=type_node.start_point[1],
                        ref_kind="property_type",
                    ))

    def _extract_field_types(self, tree, file_path, source, results):
        cursor = self._QueryCursor(self._field_query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            type_nodes = captures.get("field_type", [])
            for node in type_nodes:
                type_name = self._get_type_name(node)
                if type_name and type_name not in _PRIMITIVE_TYPES:
                    results.append(TypeRef(
                        owner_full_name="",  # Placeholder — resolved by SymbolResolver
                        type_name=type_name,
                        line=node.start_point[0], col=node.start_point[1],
                        ref_kind="field_type",
                    ))

    def _get_type_name(self, node) -> str | None:
        """Extract the simple type name from a type node, handling generic and qualified types."""
        text = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text
        if not text:
            return None
        # For generic types like List<Foo>, extract Foo (the type argument)
        # For nullable types like Foo?, extract Foo
        # For arrays like Foo[], extract Foo
        # For simple types, return as-is
        text = text.rstrip("?").rstrip("[]")
        # Strip generic wrapper — we care about the inner type for now
        if "<" in text:
            inner = text[text.index("<") + 1:text.rindex(">")]
            return inner.strip().split(",")[0].strip() if inner else None
        # For qualified names like Ns.Foo, take the last part
        if "." in text:
            return text.rsplit(".", 1)[-1]
        return text

    def _find_enclosing_method(self, line_0: int, method_lines: list[tuple[int, str]]) -> str | None:
        best: str | None = None
        for method_line, full_name in method_lines:
            if method_line <= line_0:
                best = full_name
            else:
                break
        return best
```

**Step 4: Run tests**

Run: `pytest tests/unit/indexer/test_type_ref_extractor.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/synapse/indexer/type_ref_extractor.py tests/unit/indexer/test_type_ref_extractor.py
git commit -m "feat: add TreeSitterTypeRefExtractor for C# type reference detection"
```

---

### Task 11: Build `SymbolResolver` coordinator

**Files:**
- Create: `src/synapse/indexer/symbol_resolver.py`
- Create: `tests/unit/indexer/test_symbol_resolver.py`

**Step 1: Write failing tests**

```python
# tests/unit/indexer/test_symbol_resolver.py
from unittest.mock import MagicMock, patch, call
from synapse.indexer.symbol_resolver import SymbolResolver


def _make_ls(root: str = "/proj") -> MagicMock:
    ls = MagicMock()
    ls.repository_root_path = root
    return ls


def test_resolver_walks_cs_files_and_calls_both_extractors(tmp_path):
    (tmp_path / "A.cs").write_text("namespace X { class A { void M() {} } }")

    conn = MagicMock()
    ls = _make_ls(str(tmp_path))
    ls.request_defining_symbol.return_value = None

    call_extractor = MagicMock()
    call_extractor.extract.return_value = []
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver.resolve(str(tmp_path), {})

    assert call_extractor.extract.call_count == 1
    assert type_ref_extractor.extract.call_count == 1


def test_resolver_opens_lsp_context_once_per_file(tmp_path):
    (tmp_path / "A.cs").write_text("namespace X { class A {} }")

    conn = MagicMock()
    ls = _make_ls(str(tmp_path))

    call_extractor = MagicMock()
    call_extractor.extract.return_value = []
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver.resolve(str(tmp_path), {})

    ls.open_file.assert_called_once()


def test_resolver_writes_calls_edge():
    conn = MagicMock()
    ls = _make_ls()

    callee_sym = {
        "name": "Helper", "kind": 6,
        "parent": {"name": "MyClass", "kind": 5, "parent": {"name": "MyNs", "kind": 3, "parent": None}}
    }
    ls.request_defining_symbol.return_value = callee_sym

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("MyNs.MyClass.Caller", "Helper", 5, 12)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", {})

    assert any("CALLS" in str(c) for c in conn.execute.call_args_list)


def test_resolver_writes_references_edge():
    conn = MagicMock()
    ls = _make_ls()

    from synapse.indexer.type_ref_extractor import TypeRef
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = [
        TypeRef(owner_full_name="Ns.C.M", type_name="UserDto", line=5, col=15, ref_kind="parameter")
    ]

    type_sym = {
        "name": "UserDto", "kind": 5,
        "parent": {"name": "MyNs", "kind": 3, "parent": None}
    }
    ls.request_defining_symbol.return_value = type_sym

    call_extractor = MagicMock()
    call_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", {})

    assert any("REFERENCES" in str(c) for c in conn.execute.call_args_list)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/indexer/test_symbol_resolver.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Write implementation**

Create `src/synapse/indexer/symbol_resolver.py`:

```python
from __future__ import annotations

import logging
import os
from pathlib import Path

from synapse.graph.connection import GraphConnection
from synapse.graph.edges import upsert_calls, upsert_references
from synapse.indexer.call_extractor import TreeSitterCallExtractor
from synapse.indexer.type_ref_extractor import TreeSitterTypeRefExtractor, TypeRef
from synapse.lsp.util import build_full_name

log = logging.getLogger(__name__)

_METHOD_KINDS = {6, 9, 12}  # Method, Constructor, Function
_TYPE_KINDS = {5, 11}  # Class, Interface


class SymbolResolver:
    """
    Walks .cs files once, runs call extraction and type reference extraction,
    then resolves both via LSP and writes CALLS and REFERENCES edges.
    """

    def __init__(
        self,
        conn: GraphConnection,
        ls: object,
        call_extractor: TreeSitterCallExtractor | None = None,
        type_ref_extractor: TreeSitterTypeRefExtractor | None = None,
    ) -> None:
        self._conn = conn
        self._ls = ls
        self._call_extractor = call_extractor or TreeSitterCallExtractor()
        self._type_ref_extractor = type_ref_extractor or TreeSitterTypeRefExtractor()

    def resolve(
        self,
        root_path: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> None:
        for file_path in self._iter_cs_files(root_path):
            try:
                source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                log.warning("Could not read %s", file_path)
                continue
            self._resolve_file(file_path, source, symbol_map)

    def resolve_single_file(
        self,
        file_path: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> None:
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            log.warning("Could not read %s", file_path)
            return
        self._resolve_file(file_path, source, symbol_map)

    def _resolve_file(
        self,
        file_path: str,
        source: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> None:
        root = self._ls.repository_root_path
        rel_path = os.path.relpath(file_path, root)

        call_sites = self._call_extractor.extract(file_path, source, symbol_map)
        type_refs = self._type_ref_extractor.extract(file_path, source, symbol_map)

        if not call_sites and not type_refs:
            return

        try:
            with self._ls.open_file(rel_path):
                for caller_full_name, _callee_simple, call_line_1, call_col_0 in call_sites:
                    self._resolve_call(caller_full_name, rel_path, call_line_1 - 1, call_col_0)
                for ref in type_refs:
                    self._resolve_type_ref(ref, rel_path)
        except Exception:
            log.warning("LSP open_file failed for %s, skipping", rel_path)

    def _resolve_call(
        self, caller_full_name: str, rel_path: str, line_0: int, col_0: int,
    ) -> None:
        try:
            symbol = self._ls.request_defining_symbol(rel_path, line_0, col_0)
        except Exception:
            return
        if symbol is None:
            return
        if symbol.get("kind") not in _METHOD_KINDS:
            return
        callee_full_name = build_full_name(symbol)
        if callee_full_name and callee_full_name != caller_full_name:
            upsert_calls(self._conn, caller_full_name, callee_full_name)

    def _resolve_type_ref(self, ref: TypeRef, rel_path: str) -> None:
        try:
            symbol = self._ls.request_defining_symbol(rel_path, ref.line, ref.col)
        except Exception:
            return
        if symbol is None:
            return
        if symbol.get("kind") not in _TYPE_KINDS:
            return
        target_full_name = build_full_name(symbol)
        if target_full_name and ref.owner_full_name:
            upsert_references(self._conn, ref.owner_full_name, target_full_name, ref.ref_kind)

    @staticmethod
    def _iter_cs_files(root_path: str):
        for path in Path(root_path).rglob("*.cs"):
            if not any(p in {".git", "bin", "obj"} for p in path.parts):
                yield str(path)
```

**Step 4: Run tests**

Run: `pytest tests/unit/indexer/test_symbol_resolver.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/synapse/indexer/symbol_resolver.py tests/unit/indexer/test_symbol_resolver.py
git commit -m "feat: add SymbolResolver coordinator for calls and type references"
```

---

### Task 12: Wire `SymbolResolver` into Indexer

**Files:**
- Modify: `src/synapse/indexer/indexer.py`
- Test: `tests/unit/indexer/test_structural_pass.py`

**Step 1: Write the failing test**

```python
def test_index_project_uses_symbol_resolver(mock_conn):
    """Verify that index_project delegates to SymbolResolver instead of CallIndexer."""
    lsp = MagicMock(spec=LSPAdapter)
    lsp.get_workspace_files.return_value = []

    with patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        indexer = Indexer(mock_conn, lsp)
        indexer.index_project("/proj", "csharp")
        MockResolver.assert_called_once()
        MockResolver.return_value.resolve.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/indexer/test_structural_pass.py::test_index_project_uses_symbol_resolver -v`
Expected: FAIL — still using CallIndexer

**Step 3: Write minimal implementation**

In `src/synapse/indexer/indexer.py`:

1. Replace the import of `CallIndexer` with `SymbolResolver`:
   ```python
   from synapse.indexer.symbol_resolver import SymbolResolver
   ```

2. Replace the call to `CallIndexer` in `index_project()` (line 65):
   ```python
   SymbolResolver(self._conn, self._lsp.language_server).resolve(root_path, symbol_map)
   ```

3. Add `SymbolResolver` to `reindex_file()` — after the structural pass, also run the resolver for the single file. This requires building a symbol_map for the file's methods:
   ```python
   def reindex_file(self, file_path: str, root_path: str) -> None:
       delete_file_nodes(self._conn, file_path)
       symbols = self._lsp.get_document_symbols(file_path)
       self._index_file_structure(file_path, root_path, symbols)

       name_to_full_names: dict[str, list[str]] = {}
       kind_map: dict[str, SymbolKind] = {}
       for sym in symbols:
           name_to_full_names.setdefault(sym.name, []).append(sym.full_name)
           kind_map[sym.full_name] = sym.kind

       try:
           with open(file_path, encoding="utf-8") as f:
               source = f.read()
           self._index_base_types(file_path, source, name_to_full_names, kind_map)
       except OSError:
           log.warning("Could not read %s for base type extraction", file_path)

       symbol_map = {
           (sym.file_path, sym.line): sym.full_name
           for sym in symbols
           if sym.kind == SymbolKind.METHOD
       }
       SymbolResolver(self._conn, self._lsp.language_server).resolve_single_file(file_path, symbol_map)
   ```

**Step 4: Run all tests**

Run: `pytest tests/unit/ -v`
Expected: All pass. The existing `CallIndexer` tests still pass (that class still exists, just isn't used from `Indexer` anymore).

**Step 5: Commit**

```bash
git add src/synapse/indexer/indexer.py tests/unit/indexer/test_structural_pass.py
git commit -m "feat: wire SymbolResolver into Indexer, replacing direct CallIndexer usage"
```

---

### Task 13: Wire `SymbolResolver` into service and update CLI

**Files:**
- Modify: `src/synapse/service.py`
- Modify: `src/synapse/mcp/tools.py`
- Modify: `src/synapse/cli/app.py`

**Step 1: Update `SynapseService.index_calls()`**

Replace the direct `CallIndexer` usage in `service.py:33-39` with `SymbolResolver`:

```python
def index_calls(self, path: str) -> None:
    """Run the relationship resolution pass on an already-structurally-indexed project."""
    from synapse.indexer.symbol_resolver import SymbolResolver
    lsp = CSharpLSPAdapter.create(path)
    symbol_map = get_method_symbol_map(self._conn)
    SymbolResolver(self._conn, lsp.language_server).resolve(path, symbol_map)
    lsp.shutdown()
```

**Step 2: Add service methods for new queries**

Add imports and methods to `service.py`:

```python
# Add to imports:
from synapse.graph.queries import find_type_references, find_dependencies

# Add methods:
def find_type_references(self, full_name: str) -> list[dict]:
    return find_type_references(self._conn, full_name)

def find_dependencies(self, full_name: str) -> list[dict]:
    return find_dependencies(self._conn, full_name)
```

**Step 3: Add MCP tools**

In `src/synapse/mcp/tools.py`:

```python
@mcp.tool()
def find_type_references(full_name: str) -> list[dict]:
    return service.find_type_references(full_name)

@mcp.tool()
def find_dependencies(full_name: str) -> list[dict]:
    return service.find_dependencies(full_name)
```

**Step 4: Add CLI commands**

In `src/synapse/cli/app.py`:

```python
@app.command("type-refs")
def type_refs(full_name: str) -> None:
    """Find all symbols that reference a type."""
    for item in _get_service().find_type_references(full_name):
        typer.echo(item)


@app.command()
def dependencies(full_name: str) -> None:
    """Find all types referenced by a symbol."""
    for item in _get_service().find_dependencies(full_name):
        typer.echo(item)
```

**Step 5: Run full test suite**

Run: `pytest tests/unit/ -v`
Expected: All pass

**Step 6: Commit**

```bash
git add src/synapse/service.py src/synapse/mcp/tools.py src/synapse/cli/app.py
git commit -m "feat: wire SymbolResolver into service, add type reference MCP tools and CLI commands"
```

---

## Phase 3: `get_context_for()`

### Task 14: Add `get_containing_type` and `get_members_overview` queries

**Files:**
- Modify: `src/synapse/graph/queries.py`
- Test: `tests/unit/graph/test_queries.py`

**Step 1: Write failing tests**

```python
# In tests/unit/graph/test_queries.py
from synapse.graph.queries import get_containing_type, get_members_overview

def test_get_containing_type_returns_parent() -> None:
    conn = _conn([[{"full_name": "Ns.MyClass", "name": "MyClass", "kind": "class", "line": 5, "end_line": 50}]])
    result = get_containing_type(conn, "Ns.MyClass.MyMethod")
    assert result["full_name"] == "Ns.MyClass"


def test_get_containing_type_returns_none_for_top_level() -> None:
    conn = _conn([])
    result = get_containing_type(conn, "Ns.MyClass")
    assert result is None


def test_get_members_overview_returns_children() -> None:
    conn = _conn([
        [{"full_name": "Ns.C.M()", "name": "M", "signature": "void M()"}],
        [{"full_name": "Ns.C.P", "name": "P", "type_name": "string"}],
    ])
    results = get_members_overview(conn, "Ns.C")
    assert len(results) == 2
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/graph/test_queries.py::test_get_containing_type_returns_parent tests/unit/graph/test_queries.py::test_get_members_overview_returns_children -v`
Expected: FAIL

**Step 3: Write implementation**

Add to `src/synapse/graph/queries.py`:

```python
def get_containing_type(conn: GraphConnection, full_name: str) -> dict | None:
    rows = conn.query(
        "MATCH (parent)-[:CONTAINS]->(n {full_name: $full_name}) "
        "WHERE parent:Class OR parent:Interface "
        "RETURN parent",
        {"full_name": full_name},
    )
    return rows[0][0] if rows else None


def get_members_overview(conn: GraphConnection, full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (n {full_name: $full_name})-[:CONTAINS]->(child) RETURN child",
        {"full_name": full_name},
    )
    return [r[0] for r in rows]
```

**Step 4: Run tests**

Run: `pytest tests/unit/graph/test_queries.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/synapse/graph/queries.py tests/unit/graph/test_queries.py
git commit -m "feat: add get_containing_type and get_members_overview queries"
```

---

### Task 15: Add `get_implemented_interfaces` query

**Files:**
- Modify: `src/synapse/graph/queries.py`
- Test: `tests/unit/graph/test_queries.py`

**Step 1: Write failing test**

```python
def test_get_implemented_interfaces_returns_interfaces() -> None:
    conn = _conn([
        [{"full_name": "Ns.IFoo", "name": "IFoo"}],
        [{"full_name": "Ns.IBar", "name": "IBar"}],
    ])
    results = get_implemented_interfaces(conn, "Ns.MyClass")
    assert len(results) == 2
```

**Step 2: Run test to verify it fails**

**Step 3: Write implementation**

```python
def get_implemented_interfaces(conn: GraphConnection, class_full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (c:Class {full_name: $full_name})-[:IMPLEMENTS]->(i:Interface) RETURN i",
        {"full_name": class_full_name},
    )
    return [r[0] for r in rows]
```

**Step 4: Run tests**

Run: `pytest tests/unit/graph/test_queries.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/synapse/graph/queries.py tests/unit/graph/test_queries.py
git commit -m "feat: add get_implemented_interfaces query"
```

---

### Task 16: Implement `get_context_for` in the service layer

**Files:**
- Modify: `src/synapse/service.py`
- Test: `tests/unit/test_service.py`

**Step 1: Write failing tests**

```python
def test_get_context_for_method_includes_all_sections(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text(
        "namespace Ns {\n"
        "    class MyClass : IFoo {\n"
        "        public UserDto GetUser(int id) {\n"
        "            return _repo.Find(id);\n"
        "        }\n"
        "    }\n"
        "}\n"
    )

    conn = MagicMock()
    svc = SynapseService(conn)

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value={"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "line": 2, "end_line": 4}),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 2, "end_line": 4}),
        get_containing_type=MagicMock(return_value={"full_name": "Ns.MyClass", "name": "MyClass", "kind": "class", "line": 1, "end_line": 5}),
        get_members_overview=MagicMock(return_value=[
            {"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "signature": "UserDto GetUser(int)"},
        ]),
        get_implemented_interfaces=MagicMock(return_value=[
            {"full_name": "Ns.IFoo", "name": "IFoo"},
        ]),
        find_callees=MagicMock(return_value=[
            {"full_name": "Ns.Repo.Find", "name": "Find", "signature": "User Find(int)"},
        ]),
        find_dependencies=MagicMock(return_value=[
            {"type": {"full_name": "Ns.UserDto", "name": "UserDto"}, "kind": "return_type"},
        ]),
    ):
        result = svc.get_context_for("Ns.MyClass.GetUser")

    assert "## Target:" in result
    assert "## Containing Type:" in result
    assert "## Implemented Interfaces" in result
    assert "## Called Methods" in result
    assert "## Parameter & Return Types" in result


def test_get_context_for_returns_none_when_symbol_not_found():
    conn = MagicMock()
    svc = SynapseService(conn)

    with patch("synapse.service.get_symbol", return_value=None):
        result = svc.get_context_for("Ns.Missing")

    assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_service.py::test_get_context_for_method_includes_all_sections tests/unit/test_service.py::test_get_context_for_returns_none_when_symbol_not_found -v`
Expected: FAIL — method doesn't exist

**Step 3: Write implementation**

Add to `src/synapse/service.py` imports:

```python
from synapse.graph.queries import (
    get_symbol, find_implementations, find_callers, find_callees,
    get_hierarchy, search_symbols, get_summary, list_summarized,
    list_projects, get_index_status, execute_readonly_query,
    get_method_symbol_map, get_symbol_source_info,
    find_type_references, find_dependencies,
    get_containing_type, get_members_overview, get_implemented_interfaces,
)
```

Add method:

```python
def get_context_for(self, full_name: str) -> str | None:
    symbol = get_symbol(self._conn, full_name)
    if symbol is None:
        return None

    sections: list[str] = []

    # Target symbol source
    source = self.get_symbol_source(full_name)
    sections.append(f"## Target: {full_name}\n\n{source or 'Source not available (re-index may be required)'}")

    # Containing type (for methods, properties, fields)
    parent = get_containing_type(self._conn, full_name)
    if parent:
        parent_fn = parent["full_name"]
        members = get_members_overview(self._conn, parent_fn)
        member_lines = []
        for m in members:
            sig = m.get("signature") or m.get("type_name") or ""
            member_lines.append(f"  {m.get('name', '?')}: {sig}")
        sections.append(
            f"## Containing Type: {parent_fn}\n\n"
            + "\n".join(member_lines)
        )

        # Implemented interfaces
        interfaces = get_implemented_interfaces(self._conn, parent_fn)
        if interfaces:
            iface_lines = []
            for iface in interfaces:
                iface_fn = iface["full_name"]
                iface_members = get_members_overview(self._conn, iface_fn)
                iface_sigs = [f"  {m.get('name', '?')}: {m.get('signature', '')}" for m in iface_members]
                iface_lines.append(f"### {iface_fn}\n" + "\n".join(iface_sigs))
            sections.append("## Implemented Interfaces\n\n" + "\n\n".join(iface_lines))

    # Called methods (for method targets)
    callees = find_callees(self._conn, full_name)
    if callees:
        callee_lines = [f"- `{c['full_name']}` — {c.get('signature', '')}" for c in callees]
        sections.append("## Called Methods\n\n" + "\n".join(callee_lines))

    # Type dependencies
    deps = find_dependencies(self._conn, full_name)
    if deps:
        dep_lines = []
        seen_types: set[str] = set()
        for dep in deps:
            type_fn = dep["type"]["full_name"]
            if type_fn in seen_types:
                continue
            seen_types.add(type_fn)
            kind = dep["kind"]
            type_members = get_members_overview(self._conn, type_fn)
            member_sigs = [f"  {m.get('name', '?')}: {m.get('signature', '') or m.get('type_name', '')}" for m in type_members]
            dep_lines.append(f"### {type_fn} ({kind})\n" + "\n".join(member_sigs))
        sections.append("## Parameter & Return Types\n\n" + "\n\n".join(dep_lines))

    return "\n\n---\n\n".join(sections)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_service.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/synapse/service.py tests/unit/test_service.py
git commit -m "feat: add get_context_for to service layer"
```

---

### Task 17: Add `get_context_for` MCP tool and CLI command

**Files:**
- Modify: `src/synapse/mcp/tools.py`
- Modify: `src/synapse/cli/app.py`

**Step 1: Add MCP tool**

In `src/synapse/mcp/tools.py`:

```python
@mcp.tool()
def get_context_for(full_name: str) -> str:
    result = service.get_context_for(full_name)
    return result or f"Symbol not found: {full_name}"
```

**Step 2: Add CLI command**

In `src/synapse/cli/app.py`:

```python
@app.command()
def context(full_name: str) -> None:
    """Get the full context needed to understand or modify a symbol."""
    result = _get_service().get_context_for(full_name)
    typer.echo(result or "Not found")
```

**Step 3: Run full test suite**

Run: `pytest tests/unit/ -v`
Expected: All pass

**Step 4: Commit**

```bash
git add src/synapse/mcp/tools.py src/synapse/cli/app.py
git commit -m "feat: add get_context_for MCP tool and CLI command"
```

---

### Task 18: Final validation and cleanup

**Step 1: Run full test suite**

Run: `pytest tests/unit/ -v`
Expected: All pass

**Step 2: Verify all new tools are registered**

Check that `tools.py` has all new tools: `get_symbol_source`, `find_type_references`, `find_dependencies`, `get_context_for`.

**Step 3: Verify all new CLI commands are registered**

Check that `app.py` has all new commands: `source`, `type-refs`, `dependencies`, `context`.

**Step 4: Update the graph schema design doc**

Add `REFERENCES` edge to `docs/plans/2026-03-08-graph-schema-design.md` in the edge types section and remove the "Out of Scope" note about REFERENCES.

**Step 5: Commit**

```bash
git add docs/plans/2026-03-08-graph-schema-design.md
git commit -m "docs: update schema design to include REFERENCES edge"
```
