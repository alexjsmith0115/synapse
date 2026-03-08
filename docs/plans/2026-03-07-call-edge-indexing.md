# Call Edge Indexing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Index `CALLS` edges into the graph as a separate post-structural pass using tree-sitter for call-site detection and the LSP for full-name resolution.

**Architecture:** Tree-sitter parses each `.cs` file to find call sites (invocation expressions) and their containing method — giving us `(caller_full_name, callee_simple_name, file, line)`. The LSP then resolves each call site via `request_defining_symbol` to get the fully-qualified callee. Unresolvable call sites are skipped. The pass runs after structural indexing, when all Method nodes already exist in the graph, so `CALLS` edges can be written with confirmed node matches.

**Tech Stack:** Python `tree-sitter>=0.24`, `tree-sitter-c-sharp>=0.23`, existing `solidlsp` `SolidLanguageServer`, FalkorDB via existing `GraphConnection`, `pytest` for unit tests.

---

## Background: What exists today

- `src/synapse/indexer/indexer.py` — `Indexer` class. Currently calls `lsp.find_method_calls(symbol)` per method in `_index_file_relationships`. This always fails for Roslyn and will be removed.
- `src/synapse/lsp/csharp.py` — `CSharpLSPAdapter`. `find_method_calls` uses `prepareCallHierarchy` (unsupported). Will be gutted to `return []`.
- `src/synapse/graph/edges.py` — `upsert_calls(conn, caller_full_name, callee_full_name)` — already exists, uses `MATCH (src:Method {full_name: $caller}), (dst:Method {full_name: $callee})`.
- `src/synapse/service.py` — `SynapseService.index_project()` creates LSP + Indexer, calls `indexer.index_project()`.
- `src/synapse/cli/app.py` — `index` command calls `service.index_project()`.
- Tests in `tests/unit/indexer/` and `tests/unit/lsp/`.

## What `request_defining_symbol` returns

`ls.request_defining_symbol(relative_path, line, col)` returns a `UnifiedSymbolInformation` dict (or `None`). Access fields via `.get()`. The helper `_build_full_name(raw)` in `csharp.py` walks the `parent` chain to reconstruct the fully-qualified name. We reuse it.

The method takes a **relative** path from the repo root, **0-indexed** line and column.

---

## Task 1: Add tree-sitter dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add dependencies**

In `pyproject.toml`, add to `dependencies`:
```toml
"tree-sitter>=0.24.0",
"tree-sitter-c-sharp>=0.23.0",
```

**Step 2: Install in dev environment**

```bash
cd /Users/alex/Dev/mcpcontext
source .venv/bin/activate
pip install "tree-sitter>=0.24.0" "tree-sitter-c-sharp>=0.23.0"
```

Expected: packages install successfully.

**Step 3: Verify**

```bash
python3 -c "import tree_sitter_c_sharp; from tree_sitter import Language; print('ok')"
```

Expected: `ok`

**Step 4: Reinstall synapse**

```bash
pipx install --force /Users/alex/Dev/mcpcontext
```

**Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add tree-sitter and tree-sitter-c-sharp dependencies"
```

---

## Task 2: Remove dead call-hierarchy code from indexer and adapter

The current `find_method_calls` in `CSharpLSPAdapter` uses `prepareCallHierarchy` which Roslyn doesn't support. The indexer's relationship pass calls it for every method and logs warnings. Both need cleanup before the new pass is added.

**Files:**
- Modify: `src/synapse/lsp/csharp.py`
- Modify: `src/synapse/indexer/indexer.py`
- Modify: `tests/unit/lsp/test_csharp_adapter.py`
- Modify: `tests/unit/indexer/test_structural_pass.py`

**Step 1: Gut `find_method_calls` in `CSharpLSPAdapter`**

In `src/synapse/lsp/csharp.py`, replace the entire `find_method_calls` method body:

```python
def find_method_calls(self, symbol: IndexSymbol) -> list[str]:
    return []
```

**Step 2: Gut `find_overridden_method` in `CSharpLSPAdapter`**

Same file — replace the entire `find_overridden_method` body (it also uses unsupported `prepareTypeHierarchy`):

```python
def find_overridden_method(self, symbol: IndexSymbol) -> str | None:
    return None
```

**Step 3: Remove call/override logic from `_index_file_relationships`**

In `src/synapse/indexer/indexer.py`, replace `_index_file_relationships` with:

```python
def _index_file_relationships(self, symbols: list[IndexSymbol]) -> None:
    for symbol in symbols:
        for base_type in symbol.base_types:
            if symbol.kind == SymbolKind.INTERFACE:
                upsert_inherits(self._conn, symbol.full_name, base_type)
            else:
                upsert_implements(self._conn, symbol.full_name, base_type)
```

Also remove the now-unused imports from `indexer.py`:
- Remove `upsert_calls`, `upsert_overrides` from the `from synapse.graph.edges import` line

**Step 4: Remove unused imports from `csharp.py`**

In `src/synapse/lsp/csharp.py`, remove these imports (no longer used):
- `import os`
- `from urllib.parse import urlparse`

**Step 5: Update `test_csharp_adapter.py`**

The tests `test_find_method_calls_returns_empty_when_no_hierarchy`, `test_find_method_calls_returns_callee_full_names`, and `test_find_method_calls_exception_returns_empty` all mock `server.send.prepare_call_hierarchy`. Since the implementation now just returns `[]`, replace those three tests with a single one:

```python
def test_find_method_calls_returns_empty() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind

    adapter = CSharpLSPAdapter(MagicMock())
    symbol = IndexSymbol(
        name="DoWork", full_name="MyNs.MyClass.DoWork", kind=SymbolKind.METHOD,
        file_path="/proj/Foo.cs", line=10, signature="public void DoWork()",
    )
    assert adapter.find_method_calls(symbol) == []


def test_find_overridden_method_returns_none() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind

    adapter = CSharpLSPAdapter(MagicMock())
    symbol = IndexSymbol(
        name="Execute", full_name="MyNs.MyClass.Execute", kind=SymbolKind.METHOD,
        file_path="/proj/Foo.cs", line=5, signature="public override void Execute()",
    )
    assert adapter.find_overridden_method(symbol) is None
```

**Step 6: Update `test_structural_pass.py`**

Remove the lines `lsp.find_method_calls.return_value = []` and `lsp.find_overridden_method.return_value = None` from any test that has them (these mocks are no longer needed since the method is not called).

**Step 7: Run tests**

```bash
source .venv/bin/activate
pytest tests/unit/ -q
```

Expected: all tests pass.

**Step 8: Commit**

```bash
git add src/synapse/lsp/csharp.py src/synapse/indexer/indexer.py \
        tests/unit/lsp/test_csharp_adapter.py \
        tests/unit/indexer/test_structural_pass.py
git commit -m "refactor: remove non-functional call hierarchy LSP code from indexer"
```

---

## Task 3: Build `TreeSitterCallExtractor`

This class parses a single `.cs` file and returns all call sites as `(caller_full_name, callee_name, line)` tuples. `caller_full_name` comes from the symbol graph (passed in as a lookup dict). `callee_name` is the simple identifier extracted from the AST.

**Files:**
- Create: `src/synapse/indexer/call_extractor.py`
- Create: `tests/unit/indexer/test_call_extractor.py`

**Step 1: Write the failing tests**

```python
# tests/unit/indexer/test_call_extractor.py
import pytest
from synapse.indexer.call_extractor import TreeSitterCallExtractor


@pytest.fixture
def extractor():
    return TreeSitterCallExtractor()


def test_extracts_simple_method_call(extractor):
    source = """
namespace MyNs {
    class MyClass {
        public void Caller() {
            Helper();
        }
        public void Helper() {}
    }
}
"""
    # symbol_map: maps (file_path, line_0indexed) -> full_name for all methods in this file
    symbol_map = {
        ("/proj/Foo.cs", 3): "MyNs.MyClass.Caller",
        ("/proj/Foo.cs", 5): "MyNs.MyClass.Helper",
    }
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    assert ("MyNs.MyClass.Caller", "Helper", 4) in results


def test_extracts_member_access_call(extractor):
    source = """
namespace MyNs {
    class MyClass {
        public void Run() {
            _service.Execute();
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 3): "MyNs.MyClass.Run"}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    assert ("MyNs.MyClass.Run", "Execute", 4) in results


def test_skips_calls_outside_known_methods(extractor):
    # A call at the class level (e.g. field initializer) with no containing method in symbol_map
    source = """
namespace MyNs {
    class MyClass {
        private int _x = Compute();
        public void Run() {}
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 4): "MyNs.MyClass.Run"}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    # Compute() has no enclosing method in symbol_map, so it's skipped
    assert all(caller == "MyNs.MyClass.Run" or callee != "Compute" for caller, callee, _ in results)


def test_returns_empty_for_empty_source(extractor):
    assert extractor.extract("/proj/Empty.cs", "", {}) == []
```

**Step 2: Run to verify failure**

```bash
pytest tests/unit/indexer/test_call_extractor.py -v
```

Expected: `ModuleNotFoundError: No module named 'synapse.indexer.call_extractor'`

**Step 3: Implement `TreeSitterCallExtractor`**

```python
# src/synapse/indexer/call_extractor.py
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Tree-sitter query: captures invocation_expression and object_creation_expression call names
_CALLS_QUERY = """
(invocation_expression
    function: [
        (identifier) @name
        (member_access_expression name: (identifier) @name)
    ]
)
(object_creation_expression
    type: [
        (identifier) @name
        (qualified_name name: (identifier) @name)
    ]
)
"""


class TreeSitterCallExtractor:
    """
    Parses a C# source file using tree-sitter and returns all call sites as
    (caller_full_name, callee_simple_name, line_1indexed) tuples.

    caller_full_name is resolved by finding the nearest enclosing method in symbol_map.
    Callee is the unqualified identifier — LSP resolution happens in a later step.
    """

    def __init__(self) -> None:
        import tree_sitter_c_sharp
        from tree_sitter import Language, Parser

        self._language = Language(tree_sitter_c_sharp.language())
        self._parser = Parser(self._language)
        self._query = self._language.query(_CALLS_QUERY)

    def extract(
        self,
        file_path: str,
        source: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> list[tuple[str, str, int]]:
        """
        :param file_path: absolute path to the file (used as key in symbol_map).
        :param source: full source text of the file.
        :param symbol_map: maps (file_path, 0-indexed line) -> method full_name.
        :returns: list of (caller_full_name, callee_simple_name, 1-indexed call line).
        """
        if not source.strip():
            return []

        try:
            tree = self._parser.parse(bytes(source, "utf-8"))
        except Exception:
            log.warning("Failed to parse %s with tree-sitter", file_path)
            return []

        # Build sorted list of (line_0indexed, full_name) for enclosing method lookup
        method_lines = sorted(
            (line, full_name)
            for (fp, line), full_name in symbol_map.items()
            if fp == file_path
        )

        results: list[tuple[str, str, int]] = []
        seen: set[tuple[str, str, int]] = set()

        captures = self._query.captures(tree.root_node)
        for node, _ in captures:
            call_line_0 = node.start_point[0]
            callee_name = source[node.start_byte:node.end_byte]
            caller = self._find_enclosing_method(call_line_0, method_lines)
            if caller is None:
                continue
            entry = (caller, callee_name, call_line_0 + 1)
            if entry not in seen:
                seen.add(entry)
                results.append(entry)

        return results

    def _find_enclosing_method(
        self, line_0: int, method_lines: list[tuple[int, str]]
    ) -> str | None:
        """Return the full_name of the nearest method definition at or before line_0."""
        best = None
        for method_line, full_name in method_lines:
            if method_line <= line_0:
                best = full_name
            else:
                break
        return best
```

**Step 4: Run the tests**

```bash
pytest tests/unit/indexer/test_call_extractor.py -v
```

Expected: all 4 tests pass.

**Step 5: Commit**

```bash
git add src/synapse/indexer/call_extractor.py tests/unit/indexer/test_call_extractor.py
git commit -m "feat: add TreeSitterCallExtractor for C# call site detection"
```

---

## Task 4: Build `CallIndexer`

`CallIndexer` orchestrates the full pass: iterates all `.cs` files, extracts call sites via tree-sitter, resolves callees via LSP `request_defining_symbol`, and writes `CALLS` edges to the graph. The LSP is passed in already-started (reusing the connection from structural indexing).

**Files:**
- Create: `src/synapse/indexer/call_indexer.py`
- Create: `tests/unit/indexer/test_call_indexer.py`

**Step 1: Write the failing tests**

```python
# tests/unit/indexer/test_call_indexer.py
from unittest.mock import MagicMock, patch, call as mcall
from synapse.indexer.call_indexer import CallIndexer


def _make_ls(root: str = "/proj") -> MagicMock:
    ls = MagicMock()
    ls.repository_root_path = root
    return ls


def test_writes_calls_edge_when_lsp_resolves_callee():
    conn = MagicMock()
    ls = _make_ls()

    # LSP resolves the call site to a known symbol
    callee_sym = {"name": "Helper", "kind": 6, "parent": {"name": "MyClass", "kind": 5, "parent": {"name": "MyNs", "kind": 3, "parent": None}}}
    ls.request_defining_symbol.return_value = callee_sym

    # symbol_map: one method known in the file
    symbol_map = {("/proj/Foo.cs", 3): "MyNs.MyClass.Caller"}

    extractor = MagicMock()
    extractor.extract.return_value = [("MyNs.MyClass.Caller", "Helper", 5)]

    indexer = CallIndexer(conn, ls, extractor=extractor)
    indexer._index_file("/proj/Foo.cs", "namespace X{}", symbol_map)

    conn.execute.assert_called_once()
    call_args = conn.execute.call_args
    assert "CALLS" in call_args[0][0]
    assert call_args[1]["caller"] == "MyNs.MyClass.Caller"
    assert call_args[1]["callee"] == "MyNs.MyClass.Helper"


def test_skips_edge_when_lsp_returns_none():
    conn = MagicMock()
    ls = _make_ls()
    ls.request_defining_symbol.return_value = None

    extractor = MagicMock()
    extractor.extract.return_value = [("MyNs.MyClass.Caller", "Unknown", 5)]

    indexer = CallIndexer(conn, ls, extractor=extractor)
    indexer._index_file("/proj/Foo.cs", "namespace X{}", {("/proj/Foo.cs", 3): "MyNs.MyClass.Caller"})

    conn.execute.assert_not_called()


def test_skips_edge_when_callee_not_a_method():
    """LSP resolves to a class, not a method — no CALLS edge should be written."""
    conn = MagicMock()
    ls = _make_ls()

    class_sym = {"name": "MyClass", "kind": 5, "parent": None}
    ls.request_defining_symbol.return_value = class_sym

    extractor = MagicMock()
    extractor.extract.return_value = [("MyNs.MyClass.Caller", "MyClass", 5)]

    indexer = CallIndexer(conn, ls, extractor=extractor)
    indexer._index_file("/proj/Foo.cs", "namespace X{}", {("/proj/Foo.cs", 3): "MyNs.MyClass.Caller"})

    conn.execute.assert_not_called()


def test_index_project_reads_all_cs_files(tmp_path):
    (tmp_path / "A.cs").write_text("namespace X { class A { void M() {} } }")
    (tmp_path / "B.cs").write_text("namespace X { class B { void N() {} } }")

    conn = MagicMock()
    ls = _make_ls(str(tmp_path))
    ls.request_defining_symbol.return_value = None

    extractor = MagicMock()
    extractor.extract.return_value = []

    indexer = CallIndexer(conn, ls, extractor=extractor)
    symbol_map: dict = {}
    indexer.index_calls(str(tmp_path), symbol_map)

    assert extractor.extract.call_count == 2
```

**Step 2: Run to verify failure**

```bash
pytest tests/unit/indexer/test_call_indexer.py -v
```

Expected: `ModuleNotFoundError: No module named 'synapse.indexer.call_indexer'`

**Step 3: Implement `CallIndexer`**

Key design notes:
- `index_calls` iterates `.cs` files (same filtering as `CSharpLSPAdapter.get_workspace_files`).
- For LSP resolution, we need a **relative** path from repo root and a **0-indexed** line/col. The call line from tree-sitter is 1-indexed, so subtract 1. Column 0 is sufficient.
- `request_defining_symbol` is called with the relative path; the LSP needs the file open first — `ls.open_file(rel_path)` returns a context manager.
- Only write a `CALLS` edge when the resolved symbol has `kind` in the method/function set (LSP kind 6=Method, 12=Function, 9=Constructor).
- `_build_full_name` is imported from `csharp.py` (it's a pure function with no side effects).

```python
# src/synapse/indexer/call_indexer.py
from __future__ import annotations

import logging
import os
from pathlib import Path

from synapse.graph.edges import upsert_calls
from synapse.graph.connection import GraphConnection
from synapse.indexer.call_extractor import TreeSitterCallExtractor
from synapse.lsp.csharp import _build_full_name

log = logging.getLogger(__name__)

# LSP SymbolKind integers that represent callable members
_METHOD_KINDS = {6, 9, 12}  # Method, Constructor, Function


class CallIndexer:
    """
    Post-structural pass that writes CALLS edges into the graph.

    Requires:
    - The structural pass (Indexer.index_project) to have already run, so all
      Method nodes exist in the graph.
    - The LSP to still be running (pass keep_lsp_running=True to Indexer).
    """

    def __init__(
        self,
        conn: GraphConnection,
        ls: object,
        extractor: TreeSitterCallExtractor | None = None,
    ) -> None:
        self._conn = conn
        self._ls = ls
        self._extractor = extractor or TreeSitterCallExtractor()

    def index_calls(
        self,
        root_path: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> None:
        """
        Index CALLS edges for all .cs files under root_path.

        :param root_path: absolute path to the repository root.
        :param symbol_map: maps (abs_file_path, 0-indexed line) -> method full_name.
                           Built from the IndexSymbol list produced by structural indexing.
        """
        for file_path in self._iter_cs_files(root_path):
            try:
                source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                log.warning("Could not read %s", file_path)
                continue
            self._index_file(file_path, source, symbol_map)

    def _index_file(
        self,
        file_path: str,
        source: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> None:
        root = self._ls.repository_root_path
        rel_path = os.path.relpath(file_path, root)

        call_sites = self._extractor.extract(file_path, source, symbol_map)
        if not call_sites:
            return

        try:
            with self._ls.open_file(rel_path):
                for caller_full_name, _callee_simple, call_line_1 in call_sites:
                    self._resolve_and_write(caller_full_name, rel_path, call_line_1 - 1, root)
        except Exception:
            log.warning("LSP open_file failed for %s, skipping call resolution", rel_path)

    def _resolve_and_write(
        self,
        caller_full_name: str,
        rel_path: str,
        line_0: int,
        root: str,
    ) -> None:
        try:
            symbol = self._ls.request_defining_symbol(rel_path, line_0, 0)
        except Exception:
            return
        if symbol is None:
            return
        if symbol.get("kind") not in _METHOD_KINDS:
            return
        callee_full_name = _build_full_name(symbol)
        if callee_full_name and callee_full_name != caller_full_name:
            upsert_calls(self._conn, caller_full_name, callee_full_name)

    @staticmethod
    def _iter_cs_files(root_path: str):
        for path in Path(root_path).rglob("*.cs"):
            if not any(p in {".git", "bin", "obj"} for p in path.parts):
                yield str(path)
```

**Step 4: Run tests**

```bash
pytest tests/unit/indexer/test_call_indexer.py -v
```

Expected: all 4 tests pass.

**Step 5: Commit**

```bash
git add src/synapse/indexer/call_indexer.py tests/unit/indexer/test_call_indexer.py
git commit -m "feat: add CallIndexer — tree-sitter + LSP call edge indexing pass"
```

---

## Task 5: Wire `CallIndexer` into `Indexer` and `SynapseService`

`Indexer.index_project` needs to build the `symbol_map` during its structural pass (it already has all `IndexSymbol` objects), then run `CallIndexer` as a second phase before shutting down the LSP. `SynapseService` exposes a new `index_calls` method and the CLI gets an `index-calls` command.

**Files:**
- Modify: `src/synapse/indexer/indexer.py`
- Modify: `src/synapse/service.py`
- Modify: `src/synapse/cli/app.py`
- Modify: `tests/unit/indexer/test_structural_pass.py`

**Step 1: Write a failing test for the wiring in `Indexer`**

Add to `tests/unit/indexer/test_structural_pass.py`:

```python
def test_index_project_runs_call_indexer_after_structural_pass():
    from unittest.mock import MagicMock, patch
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = []

    mock_call_indexer_cls = MagicMock()
    mock_call_indexer_instance = MagicMock()
    mock_call_indexer_cls.return_value = mock_call_indexer_instance

    with patch("synapse.indexer.indexer.CallIndexer", mock_call_indexer_cls):
        from synapse.indexer.indexer import Indexer
        indexer = Indexer(conn, lsp)
        indexer.index_project("/proj", "csharp")

    mock_call_indexer_instance.index_calls.assert_called_once()
```

**Step 2: Run to verify failure**

```bash
pytest tests/unit/indexer/test_structural_pass.py::test_index_project_runs_call_indexer_after_structural_pass -v
```

Expected: FAIL (CallIndexer not imported or not called).

**Step 3: Update `Indexer.index_project`**

In `src/synapse/indexer/indexer.py`:

1. Add import at top: `from synapse.indexer.call_indexer import CallIndexer`
2. Update `index_project` to build `symbol_map` and run `CallIndexer`:

```python
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

    # Phase 2: call edge indexing (requires LSP still running)
    symbol_map = {
        (sym.file_path, sym.line): sym.full_name
        for syms in symbols_by_file.values()
        for sym in syms
        if sym.kind.value == "method"
    }
    CallIndexer(self._conn, self._lsp).index_calls(root_path, symbol_map)

    if not keep_lsp_running:
        self._lsp.shutdown()
```

Note: `sym.kind.value == "method"` because `SymbolKind.METHOD.value` is `"method"` (see `interface.py`). This filters the symbol_map to only include method symbols.

**Step 4: Run the new test**

```bash
pytest tests/unit/indexer/test_structural_pass.py -v
```

Expected: all tests pass.

**Step 5: Add `index_calls` to `SynapseService`**

In `src/synapse/service.py`, add this method after `index_project`:

```python
def index_calls(self, path: str) -> None:
    """Run the call edge indexing pass on an already-indexed project."""
    from synapse.indexer.call_indexer import CallIndexer
    from synapse.indexer.call_extractor import TreeSitterCallExtractor
    lsp = CSharpLSPAdapter.create(path)
    # Re-collect symbol_map from the graph rather than re-running LSP structural pass
    result = self._conn.execute(
        "MATCH (m:Method)<-[:CONTAINS]-(f:File) RETURN m.full_name, m.line, f.path"
    )
    symbol_map = {
        (row[2], row[1]): row[0]
        for row in result
        if row[0] and row[1] is not None and row[2]
    }
    CallIndexer(self._conn, lsp._ls).index_calls(path, symbol_map)
    lsp.shutdown()
```

**Step 6: Add `index-calls` CLI command**

In `src/synapse/cli/app.py`, add after the `index` command:

```python
@app.command("index-calls")
def index_calls(path: str) -> None:
    """Index CALLS edges for an already-structurally-indexed project."""
    _get_service().index_calls(path)
    typer.echo(f"Call edges indexed for {path}")
```

**Step 7: Run all unit tests**

```bash
pytest tests/unit/ -q
```

Expected: all tests pass.

**Step 8: Commit**

```bash
git add src/synapse/indexer/indexer.py src/synapse/service.py \
        src/synapse/cli/app.py tests/unit/indexer/test_structural_pass.py
git commit -m "feat: wire CallIndexer into Indexer and expose index-calls CLI command"
```

---

## Task 6: Smoke test against the real project

This is a manual integration test. FalkorDB must be running.

**Step 1: Ensure FalkorDB is running**

```bash
docker ps | grep falkordb
```

If not running: `docker run -p 6379:6379 -it --rm falkordb/falkordb:latest`

**Step 2: Re-index the project (includes call pass)**

```bash
synapse index /Users/alex/Dev/oneonone
```

Expected: completes without Python tracebacks. May show LSP warnings but no `log.exception` output.

**Step 3: Verify CALLS edges were created**

```bash
synapse query "MATCH ()-[r:CALLS]->() RETURN count(r)"
```

Expected: a non-zero count.

**Step 4: Spot-check a specific method**

```bash
synapse callees "OneOnOne.API.Controllers.MeetingsController.CreateMeeting()"
```

Or use a method name that is known to call other methods. If unsure, find one:

```bash
synapse query "MATCH (m:Method)-[:CALLS]->(n:Method) RETURN m.full_name, n.full_name LIMIT 5"
```

Expected: real caller → callee pairs that make sense for the codebase.

**Step 5: Also test `index-calls` standalone command**

```bash
synapse index-calls /Users/alex/Dev/oneonone
synapse query "MATCH ()-[r:CALLS]->() RETURN count(r)"
```

Expected: edge count stays the same or increases (upsert is idempotent).

**Step 6: Commit if everything looks good**

```bash
git add -A
git commit -m "chore: verify call edge indexing smoke test passes"
```

---

## Task 7: Update MEMORY.md

Update `/Users/alex/.claude/projects/-Users-alex-Dev-mcpcontext/memory/MEMORY.md` to reflect:

1. `find_method_calls` and `find_overridden_method` now return `[]`/`None` stubs (dead code removed, not a limitation to work around).
2. The new `CallIndexer` pass: lives in `src/synapse/indexer/call_indexer.py`, uses tree-sitter + LSP `request_defining_symbol`, runs after structural indexing.
3. New dependency: `tree-sitter`, `tree-sitter-c-sharp`.
4. New CLI command: `synapse index-calls <path>`.

Remove the "LSP limitations" bullet from MEMORY.md that references `find_method_calls` returning empty.

---

## Notes

**`_build_full_name` import:** This function is in `csharp.py` as a module-level private function. Importing it from `call_indexer.py` creates a cross-module dependency on a private helper. If this feels wrong, move `_build_full_name` to a shared `src/synapse/lsp/utils.py` and update both importers. The plan above takes the simpler path first.

**LSP call resolution accuracy:** `request_defining_symbol` navigates to the definition at a call site's position. For `_service.Execute()`, the cursor is placed at the `Execute` identifier (column 0 is imprecise — a future improvement would compute the exact column from the tree-sitter node's `start_point[1]`). Column 0 may return the containing method's definition rather than the callee. A follow-up task should pass `node.start_point[1]` through `call_extractor` and use it in `call_indexer`.

**Symbol map accuracy:** The symbol_map uses `sym.line` from the structural pass. This is a 0-indexed line from the LSP. Verify this matches tree-sitter's 0-indexed start_point when writing call extractor tests against real files if discrepancies appear.
