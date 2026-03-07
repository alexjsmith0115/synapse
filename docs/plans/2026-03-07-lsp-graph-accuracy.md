# LSP Graph Accuracy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three defects in `CSharpLSPAdapter` so the graph has fully-qualified symbol names and real CALLS/OVERRIDES edges.

**Architecture:** All changes are confined to `src/synapse/lsp/csharp.py` and its tests. A new module-level helper `_build_full_name` is introduced first and reused by all three fixes. The solidlsp LSP APIs (`server.send.prepare_call_hierarchy`, `server.send.outgoing_calls`, `server.send.prepare_type_hierarchy`, `server.send.type_hierarchy_supertypes`) are accessed directly on `self._ls.server.send`. The language server's `repository_root_path` attribute provides the root for URI→relative-path conversion.

**Tech Stack:** Python 3.11+, solidlsp (in-tree copy), `os.path.relpath`, `urllib.parse.urlparse`, `pathlib.Path.as_uri`, pytest + unittest.mock

---

## Task 1: `_build_full_name` helper + fix `_convert`

**Files:**
- Modify: `src/synapse/lsp/csharp.py`
- Modify: `tests/unit/lsp/test_csharp_adapter.py`

**Context:**
`UnifiedSymbolInformation` TypedDicts returned by solidlsp have a `parent` field (added by Serena, not part of LSP spec). Root symbols have `parent = None`. Walking the chain gives the fully-qualified name. When `overload_idx` is present, append the parameter portion of `detail` (from `(` onward) to disambiguate overloads.

**Step 1: Write the failing tests**

Add to `tests/unit/lsp/test_csharp_adapter.py`:

```python
from synapse.lsp.csharp import _build_full_name


def test_build_full_name_root_symbol() -> None:
    raw = {"name": "MyNamespace", "kind": 3}
    assert _build_full_name(raw) == "MyNamespace"


def test_build_full_name_one_parent() -> None:
    parent = {"name": "MyNs", "kind": 3}
    raw = {"name": "MyClass", "kind": 5, "parent": parent}
    assert _build_full_name(raw) == "MyNs.MyClass"


def test_build_full_name_two_parents() -> None:
    grandparent = {"name": "MyNs", "kind": 3}
    parent = {"name": "MyClass", "kind": 5, "parent": grandparent}
    raw = {"name": "MyMethod", "kind": 6, "parent": parent}
    assert _build_full_name(raw) == "MyNs.MyClass.MyMethod"


def test_build_full_name_overload_appends_params() -> None:
    parent = {"name": "MyClass", "kind": 5}
    raw = {"name": "DoWork", "kind": 6, "parent": parent, "overload_idx": 1, "detail": "void DoWork(int x, string y)"}
    assert _build_full_name(raw) == "MyClass.DoWork(int x, string y)"


def test_build_full_name_overload_no_paren_in_detail() -> None:
    parent = {"name": "MyClass", "kind": 5}
    raw = {"name": "DoWork", "kind": 6, "parent": parent, "overload_idx": 0, "detail": "void DoWork"}
    assert _build_full_name(raw) == "MyClass.DoWork"


def test_convert_produces_qualified_full_name() -> None:
    from unittest.mock import MagicMock
    from synapse.lsp.csharp import CSharpLSPAdapter

    grandparent = {"name": "MyNs", "kind": 3, "parent": None}
    parent = {"name": "MyClass", "kind": 5, "parent": grandparent}
    symbol_raw = {
        "name": "MyMethod",
        "kind": 6,
        "parent": parent,
        "detail": "public void MyMethod()",
        "location": {"range": {"start": {"line": 10}}},
    }

    mock_doc_syms = MagicMock()
    mock_doc_syms.iter_symbols.return_value = [symbol_raw]
    mock_ls = MagicMock()
    mock_ls.request_document_symbols.return_value = mock_doc_syms

    adapter = CSharpLSPAdapter(mock_ls)
    symbols = adapter.get_document_symbols("/proj/Foo.cs")

    assert len(symbols) == 1
    assert symbols[0].full_name == "MyNs.MyClass.MyMethod"
    assert symbols[0].name == "MyMethod"
```

**Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/unit/lsp/test_csharp_adapter.py -v -k "full_name or convert_produces"
```

Expected: `ImportError: cannot import name '_build_full_name'`

**Step 3: Add `_build_full_name` to `csharp.py` and update `_convert`**

Add at module level in `src/synapse/lsp/csharp.py`, before the class definition:

```python
def _build_full_name(raw: dict) -> str:
    """Build a fully-qualified name by walking the parent chain of a UnifiedSymbolInformation."""
    name = raw.get("name", "")
    parent = raw.get("parent")
    base = f"{_build_full_name(parent)}.{name}" if parent is not None else name
    if "overload_idx" in raw:
        detail = raw.get("detail", "") or ""
        if "(" in detail:
            return f"{base}{detail[detail.index('('):]}"
    return base
```

Then in `_convert`, replace the `full_name=name` line:

```python
full_name=_build_full_name(raw),
```

**Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && pytest tests/unit/lsp/test_csharp_adapter.py -v
```

Expected: 8 PASSED (2 original + 6 new)

**Step 5: Commit**

```bash
git add src/synapse/lsp/csharp.py tests/unit/lsp/test_csharp_adapter.py
git commit -m "feat: add _build_full_name for qualified symbol names via parent chain traversal"
```

---

## Task 2: `find_overridden_method` via Type Hierarchy

**Files:**
- Modify: `src/synapse/lsp/csharp.py`
- Modify: `tests/unit/lsp/test_csharp_adapter.py`

**Context:**
`find_overridden_method(symbol)` is called for every METHOD during the indexer's relationship pass. It should return the `full_name` of the base method being overridden, or `None`.

The flow:
1. Short-circuit: if `"override"` not in `symbol.signature.lower()`, return `None`
2. Convert `symbol.file_path` to relative path via `os.path.relpath(symbol.file_path, self._ls.repository_root_path)`
3. Find the containing class via `self._ls.request_containing_symbol(rel_path, symbol.line, 0)`
4. Get class position from `class_sym["location"]`
5. Call `self._ls.server.send.prepare_type_hierarchy({"textDocument": {"uri": class_uri}, "position": class_start})`
6. For each item, call `self._ls.server.send.type_hierarchy_supertypes({"item": item})`
7. For each supertype, convert its `uri` to a relative path and call `self._ls.request_document_symbols(rel_path)`
8. Iterate the result's `.iter_symbols()`, find a symbol whose `name` matches `symbol.name`
9. Return `_build_full_name(found_symbol)` for the first match

URI → absolute path conversion: `from urllib.parse import urlparse` then `urlparse(uri).path`.

Add `import os` and `from urllib.parse import urlparse` at the top of `csharp.py`.

**Step 1: Write the failing tests**

Add to `tests/unit/lsp/test_csharp_adapter.py`:

```python
def test_find_overridden_method_non_override_returns_none() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind
    from unittest.mock import MagicMock

    adapter = CSharpLSPAdapter(MagicMock())
    symbol = IndexSymbol(
        name="DoWork", full_name="MyNs.MyClass.DoWork", kind=SymbolKind.METHOD,
        file_path="/proj/Foo.cs", line=10, signature="public void DoWork()",
    )
    assert adapter.find_overridden_method(symbol) is None


def test_find_overridden_method_returns_base_full_name() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind
    from unittest.mock import MagicMock

    mock_ls = MagicMock()
    mock_ls.repository_root_path = "/proj"

    # request_containing_symbol → containing class
    class_sym = {
        "name": "MyClass", "kind": 5,
        "location": {
            "uri": "file:///proj/Foo.cs",
            "range": {"start": {"line": 5, "character": 0}},
        },
    }
    mock_ls.request_containing_symbol.return_value = class_sym

    # prepare_type_hierarchy → one hierarchy item
    hier_item = {"name": "MyClass", "uri": "file:///proj/Foo.cs", "range": {"start": {"line": 5, "character": 0}}}
    mock_ls.server.send.prepare_type_hierarchy.return_value = [hier_item]

    # type_hierarchy_supertypes → one parent type
    parent_type = {"name": "BaseClass", "uri": "file:///proj/Base.cs", "range": {"start": {"line": 1, "character": 0}}}
    mock_ls.server.send.type_hierarchy_supertypes.return_value = [parent_type]

    # request_document_symbols → doc with matching method
    ns_sym = {"name": "MyNs", "kind": 3, "parent": None}
    base_class_sym = {"name": "BaseClass", "kind": 5, "parent": ns_sym}
    base_method_sym = {"name": "DoWork", "kind": 6, "parent": base_class_sym}
    mock_doc = MagicMock()
    mock_doc.iter_symbols.return_value = [base_method_sym]
    mock_ls.request_document_symbols.return_value = mock_doc

    adapter = CSharpLSPAdapter(mock_ls)
    symbol = IndexSymbol(
        name="DoWork", full_name="MyNs.MyClass.DoWork", kind=SymbolKind.METHOD,
        file_path="/proj/Foo.cs", line=10, signature="public override void DoWork()",
    )

    result = adapter.find_overridden_method(symbol)
    assert result == "MyNs.BaseClass.DoWork"


def test_find_overridden_method_exception_returns_none() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind
    from unittest.mock import MagicMock

    mock_ls = MagicMock()
    mock_ls.repository_root_path = "/proj"
    mock_ls.request_containing_symbol.side_effect = RuntimeError("LSP error")

    adapter = CSharpLSPAdapter(mock_ls)
    symbol = IndexSymbol(
        name="DoWork", full_name="MyNs.MyClass.DoWork", kind=SymbolKind.METHOD,
        file_path="/proj/Foo.cs", line=10, signature="public override void DoWork()",
    )
    assert adapter.find_overridden_method(symbol) is None
```

**Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/unit/lsp/test_csharp_adapter.py -v -k "overridden"
```

Expected: `test_find_overridden_method_non_override_returns_none` PASSES (it already short-circuits), the other two FAIL or ERROR.

**Step 3: Implement `find_overridden_method`**

Add `import os` and `from urllib.parse import urlparse` to the imports at the top of `csharp.py`. Then replace the current `find_overridden_method` body:

```python
def find_overridden_method(self, symbol: IndexSymbol) -> str | None:
    if "override" not in symbol.signature.lower():
        return None
    try:
        root = self._ls.repository_root_path
        rel_path = os.path.relpath(symbol.file_path, root)

        class_sym = self._ls.request_containing_symbol(rel_path, symbol.line, 0)
        if class_sym is None:
            return None

        class_loc = class_sym.get("location", {})
        class_uri = class_loc.get("uri", "")
        class_start = class_loc.get("range", {}).get("start", {})

        items = self._ls.server.send.prepare_type_hierarchy({
            "textDocument": {"uri": class_uri},
            "position": class_start,
        })
        if not items:
            return None

        for item in items:
            supertypes = self._ls.server.send.type_hierarchy_supertypes({"item": item})
            if not supertypes:
                continue
            for supertype in supertypes:
                abs_path = urlparse(supertype.get("uri", "")).path
                super_rel = os.path.relpath(abs_path, root)
                doc_syms = self._ls.request_document_symbols(super_rel)
                if doc_syms is None:
                    continue
                for s in doc_syms.iter_symbols():
                    if s.get("name") == symbol.name:
                        return _build_full_name(s)
        return None
    except Exception:
        log.exception("Failed to find overridden method for %s", symbol.full_name)
        return None
```

**Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && pytest tests/unit/lsp/test_csharp_adapter.py -v
```

Expected: 11 PASSED (8 from Task 1 + 3 new)

**Step 5: Commit**

```bash
git add src/synapse/lsp/csharp.py tests/unit/lsp/test_csharp_adapter.py
git commit -m "feat: implement find_overridden_method via LSP type hierarchy"
```

---

## Task 3: `find_method_calls` via Outgoing Call Hierarchy

**Files:**
- Modify: `src/synapse/lsp/csharp.py`
- Modify: `tests/unit/lsp/test_csharp_adapter.py`

**Context:**
`find_method_calls(symbol)` is called for every METHOD during the indexer's relationship pass. It should return a list of `full_name` strings for all methods called by `symbol`.

The flow:
1. Convert `symbol.file_path` to a URI via `Path(symbol.file_path).as_uri()` and to a relative path via `os.path.relpath`
2. Call `self._ls.server.send.prepare_call_hierarchy({"textDocument": {"uri": file_uri}, "position": {"line": symbol.line, "character": 0}})` → list of `CallHierarchyItem`
3. For each item, call `self._ls.server.send.outgoing_calls({"item": item})` → list of `CallHierarchyOutgoingCall` dicts
4. Each outgoing call dict has `"to": CallHierarchyItem` and `"fromRanges": [...]`. Use `to["uri"]` and `to["selectionRange"]["start"]` to locate the callee declaration.
5. Convert `to["uri"]` to a relative path and call `self._ls.request_defining_symbol(rel_path, line, character)` → `UnifiedSymbolInformation | None`
6. Apply `_build_full_name` to each non-None result; deduplicate via a `set`.

**Step 1: Write the failing tests**

Add to `tests/unit/lsp/test_csharp_adapter.py`:

```python
def test_find_method_calls_returns_empty_when_no_hierarchy() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind
    from unittest.mock import MagicMock

    mock_ls = MagicMock()
    mock_ls.repository_root_path = "/proj"
    mock_ls.server.send.prepare_call_hierarchy.return_value = []

    adapter = CSharpLSPAdapter(mock_ls)
    symbol = IndexSymbol(
        name="DoWork", full_name="MyNs.MyClass.DoWork", kind=SymbolKind.METHOD,
        file_path="/proj/Foo.cs", line=10, signature="public void DoWork()",
    )
    assert adapter.find_method_calls(symbol) == []


def test_find_method_calls_returns_callee_full_names() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind
    from unittest.mock import MagicMock

    mock_ls = MagicMock()
    mock_ls.repository_root_path = "/proj"

    hier_item = {
        "name": "DoWork", "kind": 6,
        "uri": "file:///proj/Foo.cs",
        "selectionRange": {"start": {"line": 10, "character": 4}},
    }
    mock_ls.server.send.prepare_call_hierarchy.return_value = [hier_item]

    callee_item = {
        "name": "Helper", "kind": 6,
        "uri": "file:///proj/Bar.cs",
        "selectionRange": {"start": {"line": 20, "character": 4}},
    }
    mock_ls.server.send.outgoing_calls.return_value = [
        {"to": callee_item, "fromRanges": [{"start": {"line": 12, "character": 8}}]},
    ]

    ns_sym = {"name": "BarNs", "kind": 3, "parent": None}
    cls_sym = {"name": "BarClass", "kind": 5, "parent": ns_sym}
    callee_sym = {"name": "Helper", "kind": 6, "parent": cls_sym}
    mock_ls.request_defining_symbol.return_value = callee_sym

    adapter = CSharpLSPAdapter(mock_ls)
    symbol = IndexSymbol(
        name="DoWork", full_name="MyNs.MyClass.DoWork", kind=SymbolKind.METHOD,
        file_path="/proj/Foo.cs", line=10, signature="public void DoWork()",
    )

    result = adapter.find_method_calls(symbol)
    assert result == ["BarNs.BarClass.Helper"]


def test_find_method_calls_exception_returns_empty() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind
    from unittest.mock import MagicMock

    mock_ls = MagicMock()
    mock_ls.repository_root_path = "/proj"
    mock_ls.server.send.prepare_call_hierarchy.side_effect = RuntimeError("LSP down")

    adapter = CSharpLSPAdapter(mock_ls)
    symbol = IndexSymbol(
        name="DoWork", full_name="MyNs.MyClass.DoWork", kind=SymbolKind.METHOD,
        file_path="/proj/Foo.cs", line=10, signature="public void DoWork()",
    )
    assert adapter.find_method_calls(symbol) == []
```

**Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/unit/lsp/test_csharp_adapter.py -v -k "method_calls"
```

Expected: `test_find_method_calls_returns_empty_when_no_hierarchy` PASSES (current stub returns `[]`), the other two FAIL.

**Step 3: Implement `find_method_calls`**

Replace the current `find_method_calls` body in `csharp.py`:

```python
def find_method_calls(self, symbol: IndexSymbol) -> list[str]:
    try:
        root = self._ls.repository_root_path
        file_uri = Path(symbol.file_path).as_uri()

        items = self._ls.server.send.prepare_call_hierarchy({
            "textDocument": {"uri": file_uri},
            "position": {"line": symbol.line, "character": 0},
        })
        if not items:
            return []

        callee_names: set[str] = set()
        for item in items:
            outgoing = self._ls.server.send.outgoing_calls({"item": item})
            if not outgoing:
                continue
            for call in outgoing:
                to = call.get("to", {})
                to_uri = to.get("uri", "")
                to_start = to.get("selectionRange", {}).get("start", {})
                abs_path = urlparse(to_uri).path
                to_rel = os.path.relpath(abs_path, root)
                defining = self._ls.request_defining_symbol(
                    to_rel, to_start.get("line", 0), to_start.get("character", 0)
                )
                if defining is not None:
                    callee_names.add(_build_full_name(defining))

        return list(callee_names)
    except Exception:
        log.exception("Failed to find method calls for %s", symbol.full_name)
        return []
```

**Step 4: Run all tests to verify they pass**

```bash
source .venv/bin/activate && pytest tests/unit/ -v
```

Expected: all PASSED (40 original + 8 new = 48 total)

**Step 5: Commit**

```bash
git add src/synapse/lsp/csharp.py tests/unit/lsp/test_csharp_adapter.py
git commit -m "feat: implement find_method_calls via LSP outgoing call hierarchy"
```

---

## Run All Unit Tests

```bash
source .venv/bin/activate && pytest tests/unit/ -v
```

Expected: 48 PASSED, no timeouts.
