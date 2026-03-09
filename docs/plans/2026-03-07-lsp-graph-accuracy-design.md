# LSP Graph Accuracy — Design

**Goal:** Fix three related defects in `CSharpLSPAdapter` that cause the graph to have unqualified symbol names and missing CALLS/OVERRIDES edges.

---

## Problem Summary

1. **`full_name` is unqualified** — `_convert` sets `full_name = name` (e.g. `"DoWork"` instead of `"MyNs.MyClass.DoWork"`). This breaks all graph edges (CONTAINS, CALLS, INHERITS, OVERRIDES) since they match by `full_name`.

2. **OVERRIDES edges missing** — `find_overridden_method` returns `None` unconditionally.

3. **CALLS edges missing** — `find_method_calls` returns `[]` unconditionally.

---

## Fix 1: Qualified `full_name` via Parent Chain Traversal

`UnifiedSymbolInformation` has a `parent: NotRequired[UnifiedSymbolInformation | None]` field (added by Serena/solidlsp, not part of the LSP spec). Root symbols have `parent = None`.

**`_build_full_name(raw: dict) -> str`** — module-level helper in `csharp.py`:
- Walk the parent chain recursively, joining with `.`
- If `overload_idx` is present in `raw`, the method is overloaded — append the parameter portion of `detail` (everything from `(` onward, e.g. `"(int x, string y)"`) to disambiguate
- OmniSharp sets `detail` for methods as `"ReturnType MethodName(params)"`, so `detail[detail.index("("):]` extracts the parameter signature

**Change to `_convert`:** replace `full_name=name` with `full_name=_build_full_name(raw)`.

---

## Fix 2: `find_overridden_method` via Type Hierarchy

Called for each method symbol during the indexer's relationship pass. Produces a OVERRIDES edge in the graph.

**Flow:**
1. Short-circuit: return `None` if `"override"` not in `symbol.signature.lower()` — the `signature` field stores `detail` which includes C# modifiers (`public override void ...`)
2. Convert `symbol.file_path` to a relative path via `os.path.relpath(symbol.file_path, self._ls.repository_root_path)`
3. Find the containing class: `self._ls.request_containing_symbol(rel_path, symbol.line, col=0)`
4. Prepare type hierarchy at the class position: `self._ls.server.send.prepare_type_hierarchy({"textDocument": {"uri": class_uri}, "position": class_start})`
5. For each returned `TypeHierarchyItem`, get supertypes: `self._ls.server.send.type_hierarchy_supertypes({"item": item})`
6. For each supertype: convert `uri` → relative path, call `self._ls.request_document_symbols(rel_path)`, iterate via `.iter_symbols()`, find a symbol with `name == symbol.name`
7. Return `_build_full_name(found_symbol)` for the first match; return `None` if no match found

URI conversion: `urllib.parse.urlparse(uri).path` → `os.path.relpath(abs_path, root)`.

Wrapped in `try/except Exception` — returns `None` on failure.

---

## Fix 3: `find_method_calls` via Outgoing Call Hierarchy

Called for each method symbol during the indexer's relationship pass. Produces CALLS edges in the graph.

**Flow:**
1. Convert `symbol.file_path` to absolute URI (`Path(file_path).as_uri()`) and relative path
2. Prepare call hierarchy: `self._ls.server.send.prepare_call_hierarchy({"textDocument": {"uri": file_uri}, "position": {"line": symbol.line, "character": 0}})`
3. For each returned `CallHierarchyItem`, get outgoing calls: `self._ls.server.send.outgoing_calls({"item": item})`
4. For each `CallHierarchyOutgoingCall.to`: extract `uri` + `selectionRange.start` (line, character)
5. Convert `uri` to relative path; call `self._ls.request_defining_symbol(rel_path, line, character)` → `UnifiedSymbolInformation | None`
6. Apply `_build_full_name` to each non-None result; collect and deduplicate

Wrapped in `try/except Exception` — returns `[]` on failure. Skips callees where `request_defining_symbol` returns `None`.

`request_defining_symbol` goes through `request_containing_symbol` internally, which populates the `parent` chain from the document symbols tree — so `_build_full_name` works correctly for cross-file callees.

---

## Files Changed

- `src/synapse/lsp/csharp.py` — all three fixes plus `_build_full_name` helper
- `tests/unit/lsp/test_csharp_adapter.py` — new unit tests for `_build_full_name`, `find_overridden_method` (mock), `find_method_calls` (mock)

---

## Testing

Unit tests mock `self._ls` and `self._ls.server.send` to verify the data pipeline without a live language server. The existing 2 protocol conformance tests remain unchanged.

Integration validation: run `pytest tests/integration/ -v -m integration` with FalkorDB running.
