# Graph Schema Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the approved graph schema — adding `Package` and `Interface` as first-class node labels, fixing hierarchical `CONTAINS` edges, and adding `IMPORTS` and base-type (`INHERITS`/`IMPLEMENTS`) edges.

**Architecture:** Eight sequential tasks, each with tests first. Tasks 1–3 update the graph layer (schema, nodes, edges). Tasks 4–6 fix the LSP and indexer structural pass to use parent-child hierarchy instead of the flat `iter_symbols()` traversal. Tasks 7–8 add two new extraction passes (imports via tree-sitter, base types via tree-sitter + LSP resolution).

**Tech Stack:** Python 3.11+, FalkorDB (`falkordb`), tree-sitter + tree-sitter-c-sharp, solidlsp, pytest

---

## Context You Must Read First

Before starting any task, read these files:
- `src/synapse/graph/schema.py` — index definitions
- `src/synapse/graph/nodes.py` — node upsert functions
- `src/synapse/graph/edges.py` — edge upsert functions
- `src/synapse/lsp/interface.py` — `IndexSymbol` dataclass and `LSPAdapter` protocol
- `src/synapse/lsp/csharp.py` — C# adapter (`_convert`, `get_document_symbols`)
- `src/synapse/indexer/indexer.py` — `Indexer` class
- `src/synapse/indexer/call_extractor.py` — tree-sitter pattern (follow for Tasks 7–8)

## Known Bugs To Fix

- `Directory -[CONTAINS]-> File` is currently broken: `upsert_contains` matches the destination via `{full_name: ...}` but `File` nodes have `path`, not `full_name`. Edges are silently never created.
- `File -[CONTAINS]-> Method/Property/Field` is created incorrectly because `iter_symbols()` is a flat traversal — nested symbols (methods inside classes) get a direct edge from File instead of from their parent Class.
- `base_types` is never populated in `CSharpLSPAdapter._convert()`, so `INHERITS` and `IMPLEMENTS` edges are never written despite having Cypher in `edges.py`.

---

### Task 1: Schema — add `Package` and `Interface` indices

**Files:**
- Modify: `src/synapse/graph/schema.py`
- Test: `tests/unit/graph/test_schema.py`

**Step 1: Write the failing tests**

Add to `tests/unit/graph/test_schema.py`:

```python
def test_schema_includes_package_index() -> None:
    conn = MagicMock()
    ensure_schema(conn)
    calls = [c[0][0] for c in conn.execute.call_args_list]
    assert any(":Package" in c for c in calls)


def test_schema_includes_interface_index() -> None:
    conn = MagicMock()
    ensure_schema(conn)
    calls = [c[0][0] for c in conn.execute.call_args_list]
    assert any(":Interface" in c for c in calls)


def test_schema_does_not_include_namespace_index() -> None:
    conn = MagicMock()
    ensure_schema(conn)
    calls = [c[0][0] for c in conn.execute.call_args_list]
    assert not any(":Namespace" in c for c in calls)
```

**Step 2: Run to verify they fail**

```bash
cd /Users/alex/Dev/mcpcontext && source .venv/bin/activate
pytest tests/unit/graph/test_schema.py -v
```

Expected: 2 FAILs (Package, Interface), 1 FAIL (Namespace still present).

**Step 3: Implement**

Replace `_INDICES` in `src/synapse/graph/schema.py`:

```python
_INDICES = [
    "CREATE INDEX FOR (n:Repository) ON (n.path)",
    "CREATE INDEX FOR (n:Directory) ON (n.path)",
    "CREATE INDEX FOR (n:File) ON (n.path)",
    "CREATE INDEX FOR (n:Package) ON (n.full_name)",
    "CREATE INDEX FOR (n:Class) ON (n.full_name)",
    "CREATE INDEX FOR (n:Interface) ON (n.full_name)",
    "CREATE INDEX FOR (n:Method) ON (n.full_name)",
    "CREATE INDEX FOR (n:Property) ON (n.full_name)",
    "CREATE INDEX FOR (n:Field) ON (n.full_name)",
]
```

**Step 4: Run tests**

```bash
pytest tests/unit/graph/test_schema.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add src/synapse/graph/schema.py tests/unit/graph/test_schema.py
git commit -m "feat: replace Namespace with Package and add Interface schema indices"
```

---

### Task 2: Nodes — `upsert_package`, `upsert_interface`, update `upsert_class`

**Files:**
- Modify: `src/synapse/graph/nodes.py`
- Test: `tests/unit/graph/test_nodes.py`

**Step 1: Write failing tests**

Add to `tests/unit/graph/test_nodes.py`:

```python
from synapse.graph.nodes import upsert_package, upsert_interface


def test_upsert_package_creates_package_node() -> None:
    conn = MagicMock()
    upsert_package(conn, "MyApp.Services", "Services")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert ":Package" in cypher
    assert params["full_name"] == "MyApp.Services"


def test_upsert_interface_creates_interface_node() -> None:
    conn = MagicMock()
    upsert_interface(conn, "MyApp.IService", "IService")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert ":Interface" in cypher
    assert params["full_name"] == "MyApp.IService"


def test_upsert_class_does_not_create_namespace_node() -> None:
    conn = MagicMock()
    upsert_class(conn, "MyApp.Foo", "Foo", "class")
    cypher = conn.execute.call_args[0][0]
    assert ":Namespace" not in cypher
```

**Step 2: Run to verify they fail**

```bash
pytest tests/unit/graph/test_nodes.py -v
```

**Step 3: Implement**

In `src/synapse/graph/nodes.py`:

1. Rename `upsert_namespace` to `upsert_package`, changing the label from `Namespace` to `Package`:

```python
def upsert_package(conn: GraphConnection, full_name: str, name: str) -> None:
    conn.execute(
        "MERGE (n:Package {full_name: $full_name}) SET n.name = $name",
        {"full_name": full_name, "name": name},
    )
```

2. Add `upsert_interface` after `upsert_package`:

```python
def upsert_interface(conn: GraphConnection, full_name: str, name: str) -> None:
    conn.execute(
        "MERGE (n:Interface {full_name: $full_name}) SET n.name = $name",
        {"full_name": full_name, "name": name},
    )
```

3. Delete `upsert_namespace` entirely (replaced by `upsert_package`).

**Step 4: Run tests**

```bash
pytest tests/unit/graph/test_nodes.py -v
```

**Step 5: Commit**

```bash
git add src/synapse/graph/nodes.py tests/unit/graph/test_nodes.py
git commit -m "feat: add upsert_package and upsert_interface node functions"
```

---

### Task 3: Edges — typed CONTAINS functions, update `upsert_implements`

The current `upsert_contains(conn, from_path, to_full_name)` has two bugs:
1. It matches the destination by `full_name`, so it silently fails for `Directory → File` (File has `path`, not `full_name`).
2. It's ambiguous — used for both `Dir→File` and `File→Class`.

We replace it with three typed functions.

**Files:**
- Modify: `src/synapse/graph/edges.py`
- Modify: `tests/unit/graph/test_edges.py`

**Step 1: Write failing tests**

Replace the existing `test_upsert_contains_uses_path_for_file_source` and add new tests in `tests/unit/graph/test_edges.py`:

```python
from synapse.graph.edges import (
    upsert_dir_contains, upsert_file_contains_symbol, upsert_contains_symbol,
    upsert_calls, upsert_inherits, upsert_implements, upsert_overrides,
)


def test_upsert_dir_contains_matches_by_path() -> None:
    conn = MagicMock()
    upsert_dir_contains(conn, "/proj", "/proj/src")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "CONTAINS" in cypher
    assert params["parent"] == "/proj"
    assert params["child"] == "/proj/src"


def test_upsert_file_contains_symbol_matches_file_by_path() -> None:
    conn = MagicMock()
    upsert_file_contains_symbol(conn, "/proj/Foo.cs", "MyNs.MyClass")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "CONTAINS" in cypher
    assert params["file"] == "/proj/Foo.cs"
    assert params["sym"] == "MyNs.MyClass"


def test_upsert_contains_symbol_matches_both_by_full_name() -> None:
    conn = MagicMock()
    upsert_contains_symbol(conn, "MyNs.MyClass", "MyNs.MyClass.DoWork()")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "CONTAINS" in cypher
    assert params["from_id"] == "MyNs.MyClass"


def test_upsert_implements_targets_interface_label() -> None:
    conn = MagicMock()
    upsert_implements(conn, "MyNs.ConcreteClass", "MyNs.IService")
    cypher = conn.execute.call_args[0][0]
    assert "IMPLEMENTS" in cypher
    assert ":Interface" in cypher
```

**Step 2: Run to verify they fail**

```bash
pytest tests/unit/graph/test_edges.py -v
```

**Step 3: Implement**

Replace the contents of `src/synapse/graph/edges.py`:

```python
from synapse.graph.connection import GraphConnection


def upsert_dir_contains(conn: GraphConnection, parent_path: str, child_path: str) -> None:
    """CONTAINS edge between two path-based nodes (Directory→Directory or Directory→File)."""
    conn.execute(
        "MATCH (src {path: $parent}), (dst {path: $child}) "
        "MERGE (src)-[:CONTAINS]->(dst)",
        {"parent": parent_path, "child": child_path},
    )


def upsert_file_contains_symbol(conn: GraphConnection, file_path: str, symbol_full_name: str) -> None:
    """CONTAINS edge from a File (matched by path) to a symbol (matched by full_name)."""
    conn.execute(
        "MATCH (src:File {path: $file}), (dst {full_name: $sym}) "
        "MERGE (src)-[:CONTAINS]->(dst)",
        {"file": file_path, "sym": symbol_full_name},
    )


def upsert_contains_symbol(conn: GraphConnection, from_full_name: str, to_full_name: str) -> None:
    """CONTAINS edge between two symbols (e.g. Class→Method, Package→Class)."""
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


def upsert_interface_inherits(conn: GraphConnection, child_full_name: str, parent_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Interface {full_name: $child}), (dst:Interface {full_name: $parent}) "
        "MERGE (src)-[:INHERITS]->(dst)",
        {"child": child_full_name, "parent": parent_full_name},
    )


def upsert_implements(conn: GraphConnection, class_full_name: str, interface_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Class {full_name: $cls}), (dst:Interface {full_name: $iface}) "
        "MERGE (src)-[:IMPLEMENTS]->(dst)",
        {"cls": class_full_name, "iface": interface_full_name},
    )


def upsert_overrides(conn: GraphConnection, method_full_name: str, base_method_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Method {full_name: $method}), (dst:Method {full_name: $base}) "
        "MERGE (src)-[:OVERRIDES]->(dst)",
        {"method": method_full_name, "base": base_method_full_name},
    )
```

Note: `upsert_contains` and `upsert_references` are removed. If the compiler complains about any import, fix it.

**Step 4: Run tests**

```bash
pytest tests/unit/graph/ -v
```

Expected: all PASS. Fix any import errors in other files that previously imported `upsert_contains`.

**Step 5: Commit**

```bash
git add src/synapse/graph/edges.py tests/unit/graph/test_edges.py
git commit -m "feat: replace upsert_contains with typed CONTAINS edge functions"
```

---

### Task 4: `IndexSymbol` — add `parent_full_name` field

This field lets the indexer know whether a symbol is a top-level child of the file or nested inside another symbol, without needing to re-traverse the LSP tree.

**Files:**
- Modify: `src/synapse/lsp/interface.py`
- Test: `tests/unit/lsp/test_csharp_adapter.py`

**Step 1: Write failing test**

Add to `tests/unit/lsp/test_csharp_adapter.py`:

```python
def test_index_symbol_has_parent_full_name_field() -> None:
    from synapse.lsp.interface import IndexSymbol, SymbolKind
    sym = IndexSymbol(
        name="DoWork", full_name="MyNs.MyClass.DoWork",
        kind=SymbolKind.METHOD, file_path="/proj/Foo.cs", line=10,
        parent_full_name="MyNs.MyClass",
    )
    assert sym.parent_full_name == "MyNs.MyClass"


def test_index_symbol_parent_full_name_defaults_to_none() -> None:
    from synapse.lsp.interface import IndexSymbol, SymbolKind
    sym = IndexSymbol(
        name="MyClass", full_name="MyNs.MyClass",
        kind=SymbolKind.CLASS, file_path="/proj/Foo.cs", line=1,
    )
    assert sym.parent_full_name is None
```

**Step 2: Run to verify they fail**

```bash
pytest tests/unit/lsp/test_csharp_adapter.py::test_index_symbol_has_parent_full_name_field tests/unit/lsp/test_csharp_adapter.py::test_index_symbol_parent_full_name_defaults_to_none -v
```

**Step 3: Implement**

In `src/synapse/lsp/interface.py`, add `parent_full_name` to `IndexSymbol` after `base_types`:

```python
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
    parent_full_name: str | None = None
    """full_name of the enclosing symbol, or None if this is a top-level symbol in the file."""
```

**Step 4: Run tests**

```bash
pytest tests/unit/lsp/ -v
```

**Step 5: Commit**

```bash
git add src/synapse/lsp/interface.py tests/unit/lsp/test_csharp_adapter.py
git commit -m "feat: add parent_full_name field to IndexSymbol"
```

---

### Task 5: `CSharpLSPAdapter` — hierarchical symbol traversal

Replace the flat `iter_symbols()` traversal with a recursive walk over `raw.root_symbols` and `children`, setting `parent_full_name` on each symbol.

**Files:**
- Modify: `src/synapse/lsp/csharp.py`
- Test: `tests/unit/lsp/test_csharp_adapter.py`

**Step 1: Write failing tests**

Add to `tests/unit/lsp/test_csharp_adapter.py`:

```python
def test_get_document_symbols_sets_parent_full_name_on_nested_symbol() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter

    grandparent = {"name": "MyNs", "kind": 3, "parent": None}
    parent_raw = {"name": "MyClass", "kind": 5, "parent": grandparent, "children": []}
    method_raw = {
        "name": "DoWork", "kind": 6, "parent": parent_raw, "children": [],
        "detail": "void DoWork()", "location": {"range": {"start": {"line": 5}}},
    }
    parent_raw["children"] = [method_raw]

    mock_doc_syms = MagicMock()
    mock_doc_syms.root_symbols = [parent_raw]
    mock_ls = MagicMock()
    mock_ls.request_document_symbols.return_value = mock_doc_syms

    adapter = CSharpLSPAdapter(mock_ls)
    symbols = adapter.get_document_symbols("/proj/Foo.cs")

    method = next(s for s in symbols if s.name == "DoWork")
    assert method.parent_full_name == "MyNs.MyClass"


def test_get_document_symbols_sets_none_parent_for_top_level() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter

    class_raw = {
        "name": "MyClass", "kind": 5, "parent": None, "children": [],
        "detail": "class MyClass", "location": {"range": {"start": {"line": 1}}},
    }

    mock_doc_syms = MagicMock()
    mock_doc_syms.root_symbols = [class_raw]
    mock_ls = MagicMock()
    mock_ls.request_document_symbols.return_value = mock_doc_syms

    adapter = CSharpLSPAdapter(mock_ls)
    symbols = adapter.get_document_symbols("/proj/Foo.cs")

    assert symbols[0].parent_full_name is None
```

**Step 2: Run to verify they fail**

```bash
pytest tests/unit/lsp/test_csharp_adapter.py -k "parent" -v
```

**Step 3: Implement**

Replace `get_document_symbols` and update `_convert` in `src/synapse/lsp/csharp.py`:

```python
def get_document_symbols(self, file_path: str) -> list[IndexSymbol]:
    try:
        raw = self._ls.request_document_symbols(file_path)
        if raw is None:
            return []
        result: list[IndexSymbol] = []
        for root in raw.root_symbols:
            self._traverse(root, file_path, parent_full_name=None, result=result)
        return result
    except Exception:
        log.exception("Failed to get symbols for %s", file_path)
        return []

def _traverse(
    self,
    raw: dict,
    file_path: str,
    parent_full_name: str | None,
    result: list[IndexSymbol],
) -> None:
    sym = self._convert(raw, file_path, parent_full_name)
    result.append(sym)
    for child in raw.get("children", []):
        self._traverse(child, file_path, parent_full_name=sym.full_name, result=result)
```

Update `_convert` signature and return to include `parent_full_name`:

```python
def _convert(self, raw: dict, file_path: str, parent_full_name: str | None = None) -> IndexSymbol:
    kind_int = raw.get("kind", 0)
    kind = _LSP_KIND_MAP.get(kind_int)
    if kind is None:
        log.debug("Unmapped LSP SymbolKind %d for symbol %s, defaulting to CLASS", kind_int, raw.get("name", "?"))
        kind = SymbolKind.CLASS
    name = raw.get("name", "")
    line = raw.get("location", {}).get("range", {}).get("start", {}).get("line", 0)
    detail = raw.get("detail", "") or ""
    return IndexSymbol(
        name=name,
        full_name=build_full_name(raw),
        kind=kind,
        file_path=file_path,
        line=line,
        signature=detail,
        is_abstract="abstract" in detail.lower(),
        is_static="static" in detail.lower(),
        parent_full_name=parent_full_name,
    )
```

**Step 4: Run all LSP tests**

```bash
pytest tests/unit/lsp/ -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add src/synapse/lsp/csharp.py tests/unit/lsp/test_csharp_adapter.py
git commit -m "feat: switch CSharpLSPAdapter to hierarchical symbol traversal, populate parent_full_name"
```

---

### Task 6: Indexer — fix containment hierarchy + directory chain + package nodes

This task wires everything together: uses `parent_full_name` to route CONTAINS edges correctly, walks the directory chain for `Directory -[CONTAINS]-> Directory`, and creates `Package -[CONTAINS]-> Class/Interface` edges.

**Files:**
- Modify: `src/synapse/indexer/indexer.py`
- Test: `tests/unit/indexer/test_structural_pass.py`

**Step 1: Write failing tests**

Add to `tests/unit/indexer/test_structural_pass.py`:

```python
def _make_nested_symbol(
    parent_full_name: str, name: str, kind: SymbolKind, file_path: str = "/proj/Foo.cs"
) -> IndexSymbol:
    return IndexSymbol(
        name=name,
        full_name=f"{parent_full_name}.{name}",
        kind=kind,
        file_path=file_path,
        line=10,
        parent_full_name=parent_full_name,
    )


def test_nested_symbol_gets_contains_from_parent_not_file() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = [
        _make_symbol("MyClass", SymbolKind.CLASS),
        _make_nested_symbol("MyNs.MyClass", "DoWork", SymbolKind.METHOD),
    ]

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    calls = [str(c) for c in conn.execute.call_args_list]
    # Parent-to-child edge must use full_name (symbol→symbol), not file path
    assert any("MyNs.MyClass" in c and "DoWork" in c and "CONTAINS" in c for c in calls)


def test_top_level_symbol_gets_contains_from_file() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = [
        _make_symbol("MyClass", SymbolKind.CLASS),
    ]

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("/proj/Foo.cs" in c and "MyNs.MyClass" in c and "CONTAINS" in c for c in calls)


def test_directory_chain_creates_dir_contains_dir() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/src/Foo.cs"]
    lsp.get_document_symbols.return_value = []

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("/proj" in c and "/proj/src" in c and "CONTAINS" in c for c in calls)
```

**Step 2: Run to verify they fail**

```bash
pytest tests/unit/indexer/test_structural_pass.py -v
```

**Step 3: Implement**

Replace `src/synapse/indexer/indexer.py` with the following (preserve imports, just rewrite the class):

```python
from __future__ import annotations

import logging
import os

from synapse.graph.connection import GraphConnection
from synapse.graph.edges import (
    upsert_contains_symbol, upsert_dir_contains, upsert_file_contains_symbol,
    upsert_inherits, upsert_interface_inherits, upsert_implements,
)
from synapse.graph.nodes import (
    upsert_class, upsert_directory, upsert_field, upsert_file,
    upsert_interface, upsert_method, upsert_package, upsert_property,
    upsert_repository, delete_file_nodes,
)
from synapse.indexer.call_indexer import CallIndexer
from synapse.lsp.interface import IndexSymbol, LSPAdapter, SymbolKind

log = logging.getLogger(__name__)


class Indexer:
    def __init__(self, conn: GraphConnection, lsp: LSPAdapter) -> None:
        self._conn = conn
        self._lsp = lsp

    def index_project(self, root_path: str, language: str, keep_lsp_running: bool = False) -> None:
        files = self._lsp.get_workspace_files(root_path)
        symbols_by_file: dict[str, list[IndexSymbol]] = {}

        for file_path in files:
            symbols = self._lsp.get_document_symbols(file_path)
            symbols_by_file[file_path] = symbols
            self._index_file_structure(file_path, root_path, symbols)

        for symbols in symbols_by_file.values():
            self._index_file_relationships(symbols)

        upsert_repository(self._conn, root_path, language)

        symbol_map = {
            (sym.file_path, sym.line): sym.full_name
            for syms in symbols_by_file.values()
            for sym in syms
            if sym.kind == SymbolKind.METHOD
        }
        CallIndexer(self._conn, self._lsp.language_server).index_calls(root_path, symbol_map)

        if not keep_lsp_running:
            self._lsp.shutdown()

    def reindex_file(self, file_path: str, root_path: str) -> None:
        delete_file_nodes(self._conn, file_path)
        symbols = self._lsp.get_document_symbols(file_path)
        self._index_file_structure(file_path, root_path, symbols)
        self._index_file_relationships(symbols)

    def delete_file(self, file_path: str) -> None:
        delete_file_nodes(self._conn, file_path)

    def _index_file_structure(self, file_path: str, root_path: str, symbols: list[IndexSymbol]) -> None:
        self._upsert_directory_chain(file_path, root_path)
        upsert_file(self._conn, file_path, os.path.basename(file_path), "csharp")

        for symbol in symbols:
            self._upsert_symbol(symbol)
            if symbol.parent_full_name is None:
                upsert_file_contains_symbol(self._conn, file_path, symbol.full_name)
            else:
                upsert_contains_symbol(self._conn, symbol.parent_full_name, symbol.full_name)

    def _upsert_directory_chain(self, file_path: str, root_path: str) -> None:
        """Walk from file's directory up to root_path, upserting directories and CONTAINS edges."""
        dirs: list[str] = []
        current = os.path.dirname(file_path)
        while True:
            dirs.append(current)
            if current == root_path or current == os.path.dirname(current):
                break
            current = os.path.dirname(current)

        dirs.reverse()  # root-first

        for dir_path in dirs:
            upsert_directory(self._conn, dir_path, os.path.basename(dir_path) or dir_path)

        for i in range(len(dirs) - 1):
            upsert_dir_contains(self._conn, dirs[i], dirs[i + 1])

        upsert_dir_contains(self._conn, dirs[-1], file_path)

    def _upsert_symbol(self, symbol: IndexSymbol) -> None:
        match symbol.kind:
            case SymbolKind.NAMESPACE:
                upsert_package(self._conn, symbol.full_name, symbol.name)
            case SymbolKind.INTERFACE:
                upsert_interface(self._conn, symbol.full_name, symbol.name)
            case SymbolKind.CLASS | SymbolKind.ABSTRACT_CLASS | SymbolKind.ENUM | SymbolKind.RECORD:
                upsert_class(self._conn, symbol.full_name, symbol.name, symbol.kind.value)
            case SymbolKind.METHOD:
                upsert_method(self._conn, symbol.full_name, symbol.name, symbol.signature, symbol.is_abstract, symbol.is_static, symbol.line)
            case SymbolKind.PROPERTY:
                upsert_property(self._conn, symbol.full_name, symbol.name, "")
            case SymbolKind.FIELD:
                upsert_field(self._conn, symbol.full_name, symbol.name, "")
            case _:
                log.debug("Skipping symbol of unhandled kind: %s", symbol.kind)

    def _index_file_relationships(self, symbols: list[IndexSymbol]) -> None:
        for symbol in symbols:
            for base_type in symbol.base_types:
                if symbol.kind == SymbolKind.INTERFACE:
                    upsert_interface_inherits(self._conn, symbol.full_name, base_type)
                elif symbol.kind in (SymbolKind.CLASS, SymbolKind.ABSTRACT_CLASS, SymbolKind.RECORD):
                    # base_type is a Class (INHERITS) or Interface (IMPLEMENTS).
                    # At index time we don't know which; the edge function's MATCH labels will
                    # silently no-op if the target node has the wrong label.
                    upsert_inherits(self._conn, symbol.full_name, base_type)
                    upsert_implements(self._conn, symbol.full_name, base_type)
```

**Step 4: Run all unit tests**

```bash
pytest tests/unit/ -v
```

Expected: all PASS. Fix any import errors.

**Step 5: Commit**

```bash
git add src/synapse/indexer/indexer.py tests/unit/indexer/test_structural_pass.py
git commit -m "feat: fix hierarchical CONTAINS edges and directory chain in Indexer"
```

---

### Task 7: Import extraction — `File -[IMPORTS]-> Package`

Parse `using` directives from C# source files using tree-sitter to create `File -[IMPORTS]-> Package` edges.

**Files:**
- Create: `src/synapse/indexer/import_extractor.py`
- Create: `tests/unit/indexer/test_import_extractor.py`
- Modify: `src/synapse/indexer/indexer.py`

**Step 1: Write failing tests**

Create `tests/unit/indexer/test_import_extractor.py`:

```python
import pytest
from synapse.indexer.import_extractor import CSharpImportExtractor


@pytest.fixture()
def extractor() -> CSharpImportExtractor:
    return CSharpImportExtractor()


def test_extract_simple_using(extractor: CSharpImportExtractor) -> None:
    source = "using System.Collections.Generic;\nclass Foo {}"
    result = extractor.extract("/proj/Foo.cs", source)
    assert "System.Collections.Generic" in result


def test_extract_multiple_usings(extractor: CSharpImportExtractor) -> None:
    source = "using System;\nusing System.IO;\nclass Foo {}"
    result = extractor.extract("/proj/Foo.cs", source)
    assert "System" in result
    assert "System.IO" in result


def test_extract_ignores_static_using(extractor: CSharpImportExtractor) -> None:
    # using static directives reference types, not packages — exclude them
    source = "using static System.Math;\nclass Foo {}"
    result = extractor.extract("/proj/Foo.cs", source)
    assert result == []


def test_extract_empty_file(extractor: CSharpImportExtractor) -> None:
    assert extractor.extract("/proj/Foo.cs", "") == []
```

**Step 2: Run to verify they fail**

```bash
pytest tests/unit/indexer/test_import_extractor.py -v
```

**Step 3: Implement**

Create `src/synapse/indexer/import_extractor.py`:

```python
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Matches: using Some.Namespace;
# Excludes: using static Some.Type;  (static keyword present as sibling)
_IMPORTS_QUERY = """
(using_directive
  !static
  [(identifier) @name
   (qualified_name) @name])
"""


class CSharpImportExtractor:
    """Parses C# source files and returns all imported package names from using directives."""

    def __init__(self) -> None:
        import tree_sitter_c_sharp
        from tree_sitter import Language, Parser, Query, QueryCursor

        self._language = Language(tree_sitter_c_sharp.language())
        self._parser = Parser(self._language)
        self._query = Query(self._language, _IMPORTS_QUERY)
        self._QueryCursor = QueryCursor

    def extract(self, file_path: str, source: str) -> list[str]:
        """Return list of package full_names imported by this file."""
        if not source.strip():
            return []
        try:
            tree = self._parser.parse(bytes(source, "utf-8"))
        except Exception:
            log.warning("tree-sitter failed to parse %s", file_path)
            return []

        results: list[str] = []
        seen: set[str] = set()
        cursor = self._QueryCursor(self._query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            for node in captures.get("name", []):
                name = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text
                if name not in seen:
                    seen.add(name)
                    results.append(name)
        return results
```

> **Note:** The tree-sitter query for `using_directive` may need adjustment depending on the exact C# grammar version. The `!static` negation predicate filters out `using static` directives. If this syntax isn't supported, parse the node text and skip entries starting with `static`.

**Step 4: Wire into indexer**

In `src/synapse/indexer/indexer.py`:

1. Add import at top:
```python
from synapse.indexer.import_extractor import CSharpImportExtractor
from synapse.graph.edges import upsert_imports  # add this function in edges.py first (see below)
```

2. Add `upsert_imports` to `src/synapse/graph/edges.py`:
```python
def upsert_imports(conn: GraphConnection, file_path: str, package_full_name: str) -> None:
    conn.execute(
        "MATCH (src:File {path: $file}), (dst:Package {full_name: $pkg}) "
        "MERGE (src)-[:IMPORTS]->(dst)",
        {"file": file_path, "pkg": package_full_name},
    )
```

3. Add `_import_extractor` to `Indexer.__init__`:
```python
self._import_extractor = CSharpImportExtractor()
```

4. Add import pass to `_index_file_structure`, after `upsert_file`:
```python
try:
    with open(file_path, encoding="utf-8") as f:
        source = f.read()
    for pkg_name in self._import_extractor.extract(file_path, source):
        upsert_imports(self._conn, file_path, pkg_name)
except OSError:
    log.warning("Could not read %s for import extraction", file_path)
```

**Step 5: Run tests**

```bash
pytest tests/unit/ -v
```

**Step 6: Commit**

```bash
git add src/synapse/indexer/import_extractor.py tests/unit/indexer/test_import_extractor.py src/synapse/indexer/indexer.py src/synapse/graph/edges.py
git commit -m "feat: add CSharpImportExtractor and File-[IMPORTS]->Package edges"
```

---

### Task 8: Base type extraction — `INHERITS` and `IMPLEMENTS` edges

Parse C# class/interface declarations with tree-sitter to find base type simple names, then resolve them to full names using the symbol map (same approach as `CallIndexer`).

**Files:**
- Create: `src/synapse/indexer/base_type_extractor.py`
- Create: `tests/unit/indexer/test_base_type_extractor.py`
- Modify: `src/synapse/indexer/indexer.py`

**C# inheritance rule:** In C#, the base list `class Foo : Bar, IBaz, IQux` has exactly one rule — the first entry is the base class if it is a class, and all entries are interfaces if the type is an interface or if the first entry is an interface. The extractor encodes this by returning `(type_name, base_name, is_first)` triples so the indexer can apply the rule without guessing.

**Step 1: Write failing tests**

Create `tests/unit/indexer/test_base_type_extractor.py`:

```python
import pytest
from synapse.indexer.base_type_extractor import CSharpBaseTypeExtractor


@pytest.fixture()
def extractor() -> CSharpBaseTypeExtractor:
    return CSharpBaseTypeExtractor()


def test_extract_class_with_base_class(extractor: CSharpBaseTypeExtractor) -> None:
    source = "class Dog : Animal {}"
    result = extractor.extract("/proj/Dog.cs", source)
    # (type_name, base_name, is_first)
    assert ("Dog", "Animal", True) in result


def test_extract_class_implementing_interface(extractor: CSharpBaseTypeExtractor) -> None:
    source = "class UserService : IUserService {}"
    result = extractor.extract("/proj/UserService.cs", source)
    assert ("UserService", "IUserService", True) in result


def test_extract_class_with_multiple_bases_marks_first(extractor: CSharpBaseTypeExtractor) -> None:
    source = "class Repo : BaseRepo, IRepo, IDisposable {}"
    result = extractor.extract("/proj/Repo.cs", source)
    first_flags = {base: is_first for _, base, is_first in result}
    assert first_flags["BaseRepo"] is True
    assert first_flags["IRepo"] is False
    assert first_flags["IDisposable"] is False


def test_extract_interface_inheriting_interface(extractor: CSharpBaseTypeExtractor) -> None:
    source = "interface IService : IDisposable {}"
    result = extractor.extract("/proj/IService.cs", source)
    assert ("IService", "IDisposable", True) in result


def test_extract_no_bases(extractor: CSharpBaseTypeExtractor) -> None:
    source = "class Foo {}"
    result = extractor.extract("/proj/Foo.cs", source)
    assert result == []
```

**Step 2: Run to verify they fail**

```bash
pytest tests/unit/indexer/test_base_type_extractor.py -v
```

**Step 3: Implement**

Create `src/synapse/indexer/base_type_extractor.py`:

```python
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_BASE_TYPES_QUERY = """
(class_declaration
    name: (identifier) @type_name
    bases: (base_list
        [(identifier) @base
         (generic_name name: (identifier) @base)]))

(interface_declaration
    name: (identifier) @type_name
    bases: (base_list
        [(identifier) @base
         (generic_name name: (identifier) @base)]))
"""


class CSharpBaseTypeExtractor:
    """
    Parses C# source and returns (type_simple_name, base_simple_name, is_first) triples.

    is_first=True marks the first entry in the base list. In C#, the first entry is the
    base class if the declaring type is a class; remaining entries are always interfaces.
    Callers must resolve simple names to full_names using the symbol map.
    """

    def __init__(self) -> None:
        import tree_sitter_c_sharp
        from tree_sitter import Language, Parser, Query, QueryCursor

        self._language = Language(tree_sitter_c_sharp.language())
        self._parser = Parser(self._language)
        self._query = Query(self._language, _BASE_TYPES_QUERY)
        self._QueryCursor = QueryCursor

    def extract(self, file_path: str, source: str) -> list[tuple[str, str, bool]]:
        """
        Return list of (type_simple_name, base_simple_name, is_first) triples.
        Does not resolve to full_names — that requires LSP or symbol map lookup.
        """
        if not source.strip():
            return []
        try:
            tree = self._parser.parse(bytes(source, "utf-8"))
        except Exception:
            log.warning("tree-sitter failed to parse %s", file_path)
            return []

        results: list[tuple[str, str, bool]] = []
        cursor = self._QueryCursor(self._query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            type_nodes = captures.get("type_name", [])
            base_nodes = captures.get("base", [])
            if not type_nodes:
                continue
            type_name = (type_nodes[0].text.decode("utf-8") if isinstance(type_nodes[0].text, bytes) else type_nodes[0].text)
            for i, base_node in enumerate(base_nodes):
                base_name = (base_node.text.decode("utf-8") if isinstance(base_node.text, bytes) else base_node.text)
                results.append((type_name, base_name, i == 0))
        return results
```

**Step 4: Wire into indexer**

The base type extractor returns simple names. We resolve them using the existing symbol map (name → full_name). Add a `_resolve_base_types` pass to `Indexer`.

In `src/synapse/indexer/indexer.py`:

1. Add import: `from synapse.indexer.base_type_extractor import CSharpBaseTypeExtractor`
2. Add `self._base_type_extractor = CSharpBaseTypeExtractor()` in `__init__`
3. Build a name-to-full_name lookup during `index_project` and call `_index_base_types`:

```python
# After the structural pass loop, before upsert_repository:
name_to_full_names: dict[str, list[str]] = {}
for syms in symbols_by_file.values():
    for sym in syms:
        name_to_full_names.setdefault(sym.name, []).append(sym.full_name)

for file_path in files:
    try:
        with open(file_path, encoding="utf-8") as f:
            source = f.read()
        self._index_base_types(file_path, source, name_to_full_names)
    except OSError:
        log.warning("Could not read %s for base type extraction", file_path)
```

4. Add the method:

```python
def _index_base_types(
    self,
    file_path: str,
    source: str,
    name_to_full_names: dict[str, list[str]],
    kind_map: dict[str, SymbolKind],
) -> None:
    triples = self._base_type_extractor.extract(file_path, source)
    for type_simple, base_simple, is_first in triples:
        type_candidates = name_to_full_names.get(type_simple, [])
        base_candidates = name_to_full_names.get(base_simple, [])
        for type_full in type_candidates:
            type_kind = kind_map.get(type_full)
            for base_full in base_candidates:
                if type_kind == SymbolKind.INTERFACE:
                    # Interface can only extend another interface
                    upsert_interface_inherits(self._conn, type_full, base_full)
                elif is_first:
                    # C# rule: first base of a class is the base class (INHERITS),
                    # unless no Class node exists for it (then it's an interface: IMPLEMENTS).
                    # Attempt both; typed MATCH labels ensure only the correct one writes.
                    upsert_inherits(self._conn, type_full, base_full)
                    upsert_implements(self._conn, type_full, base_full)
                else:
                    # Non-first entries in a class base list are always interfaces
                    upsert_implements(self._conn, type_full, base_full)
```

Also build `kind_map` before calling `_index_base_types`:

```python
kind_map: dict[str, SymbolKind] = {
    sym.full_name: sym.kind
    for syms in symbols_by_file.values()
    for sym in syms
}
```

And pass it: `self._index_base_types(file_path, source, name_to_full_names, kind_map)`

> **Note:** Name resolution is best-effort. If two types share the same simple name in different namespaces, both candidates are attempted; the typed MATCH constraints in the edge functions ensure only valid edges are written.

**Step 5: Run all unit tests**

```bash
pytest tests/unit/ -v
```

Expected: all PASS.

**Step 6: Commit**

```bash
git add src/synapse/indexer/base_type_extractor.py tests/unit/indexer/test_base_type_extractor.py src/synapse/indexer/indexer.py
git commit -m "feat: add CSharpBaseTypeExtractor and INHERITS/IMPLEMENTS edge population"
```

---

## TODOs (out of scope for this plan)

- **Method parameters as a node property** — `upsert_method` currently stores `signature` (the raw detail string from LSP, e.g. `"public void DoWork(int id, string name)"`). A future task should parse the signature to extract a structured `parameters` field (e.g. `[{"name": "id", "type": "int"}, {"name": "name", "type": "string"}]`) and store it as a JSON property on `Method` nodes. This enables queries like "find all methods that take a `CancellationToken`" without creating separate `Parameter` nodes (which would add significant graph complexity for limited query benefit).

---

## Final Verification

```bash
pytest tests/unit/ -v
```

All tests should pass. Integration tests require FalkorDB and .NET:

```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb:latest
pytest tests/integration/ -v -m integration
```
