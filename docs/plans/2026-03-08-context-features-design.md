# Context Features Design

**Date:** 2026-03-08
**Status:** Approved

## Overview

Three features to transform Synapse from a structural index into a context engine for LLM coding agents. Implemented in three phases using Approach C (parallel infrastructure + feature).

- **Phase 1:** Line ranges on nodes + `get_symbol_source()` tool
- **Phase 2:** `SymbolResolver` (refactored Phase 2 pass) + type reference edges + query tools
- **Phase 3:** `get_context_for()` — contextual retrieval tool

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Source code storage | Line ranges on nodes, read from disk on demand | Lightweight, never stale, filesystem always available |
| Line range source | LSP `location.range.end.line` | Already returned by LSP, just not captured |
| Type dep scope | Signatures only (params, returns, property/field types) | Covers public API coupling; most impactful for correctness |
| Type resolution | LSP `request_defining_symbol` | Accurate; matches existing call indexing pattern |
| Contextual retrieval output | Structured markdown sections | Natural for LLM consumption |
| Phase 2 architecture | Single pass via `SymbolResolver` | Avoids duplicate file walks and LSP open/close overhead |
| Incremental re-indexing | Full Phase 1 + Phase 2 for changed files | Watcher keeps LSP alive; per-file Phase 2 is fast |
| Type edge naming | `REFERENCES` with `kind` property | Simple schema, filterable via kind (parameter, return_type, field_type, property_type) |

---

## Phase 1: Line Ranges & `get_symbol_source()`

### Data Model Changes

**`IndexSymbol`** — add `end_line: int` field (default 0).

**`CSharpLSPAdapter._convert()`** — capture `location.range.end.line` from LSP response.

**Node upsert functions** — `upsert_method()`, `upsert_class()`, `upsert_interface()`, `upsert_property()`, `upsert_field()` all gain an `end_line` parameter, stored as a node property.

### New Query

`get_symbol_source()` in `queries.py`: look up a node by `full_name`, return `file_path`, `line`, `end_line`.

### New Service Method + MCP Tool

```
get_symbol_source(full_name: str, include_class_signature: bool = False) -> str
```

1. Query graph for the node's `file_path`, `line`, `end_line`
2. Read lines `line..end_line` from disk
3. If `include_class_signature=True` and the symbol is a Method/Property/Field, also query the parent Class/Interface node and prepend its signature line
4. Return formatted source with file path header

### Schema Migration

Existing indexed projects won't have `end_line`. Tools treat `end_line=0` or missing as "unknown" and return an error suggesting re-index.

---

## Phase 2: SymbolResolver & Type Reference Edges

### SymbolResolver

Replaces direct `CallIndexer` usage. New class in `src/synapse/indexer/symbol_resolver.py`.

- Owns the file tree walk and LSP file open/close lifecycle
- For each .cs file: reads source, opens LSP context, runs all extractors, closes context
- Extractors: `CallExtractor` (refactored from `CallIndexer`) and `TypeRefExtractor` (new)

### CallExtractor

Rename/refactor from `CallIndexer`. Receives `(file_path, source, symbol_map, lsp)` per file. Logic unchanged, just reorganized to fit the coordinator pattern.

### TypeRefExtractor

New class in `src/synapse/indexer/type_ref_extractor.py`. Uses tree-sitter to find type positions in:

- **Method parameters** — walk `parameter_list` nodes, find type annotations
- **Method return types** — walk `method_declaration` nodes, get return type
- **Property types** — walk `property_declaration`, get type
- **Field types** — walk `field_declaration`, get type

For each type position, records `(owner_full_name, type_name, line, col, ref_kind)` where `ref_kind` is one of `"parameter"`, `"return_type"`, `"field_type"`, `"property_type"`.

### LSP Resolution

Same pattern as call indexing: `request_defining_symbol(rel_path, line, col)` at each type position. If it resolves to a Class/Interface node in the graph, write a `REFERENCES` edge with `kind` property.

### REFERENCES Edge

```
(Method)-[:REFERENCES {kind: "parameter"}]->(Class|Interface)
(Method)-[:REFERENCES {kind: "return_type"}]->(Class|Interface)
(Property)-[:REFERENCES {kind: "property_type"}]->(Class|Interface)
(Field)-[:REFERENCES {kind: "field_type"}]->(Class|Interface)
```

Edge upsert in `edges.py`: `upsert_references(source_full_name, target_full_name, kind)`.

### New Queries & MCP Tools

**`find_type_references(full_name)`** — Given a Class/Interface, find all symbols that reference it (with kind). Reverse direction: "who uses this type?"

**`find_dependencies(full_name)`** — Given a Method/Property/Field, find all types it references. Forward direction: "what types does this depend on?"

### Wiring

- `Indexer.index_project()` calls `SymbolResolver` instead of `CallIndexer` directly
- `Indexer.reindex_file()` runs `SymbolResolver` for the single changed file
- `SynapseService.index_calls()` updated to use `SymbolResolver` (backward compat for CLI)

---

## Phase 3: `get_context_for()`

### Tool Signature

```
get_context_for(full_name: str) -> str
```

### Output for Method Target

```
## Target: Namespace.Class.Method
<method source code>

## Containing Type: Namespace.Class
<class/interface declaration line + member signatures (no bodies)>

## Implemented Interfaces
<interface declaration + method signatures for any interface the containing class implements>

## Called Methods
<signature of each method this method calls>

## Parameter & Return Types
<for each referenced type: declaration line + member signatures (no bodies)>
```

### Output for Class/Interface Target

```
## Target: Namespace.Class
<class declaration + all member signatures (no bodies)>

## Inheritance
<parent class signature, if any>
<implemented interfaces with their method signatures>

## Referenced Types
<types used in property/field declarations — declaration + member signatures>
```

### Output for Property/Field Target

Property source, containing type signature, and the property's type signature.

### Implementation

Pure query composition — no new indexing:

1. Query the target node (get symbol + source via line range)
2. Traverse graph edges (CONTAINS for parent, IMPLEMENTS/INHERITS for interfaces/base, CALLS for callees, REFERENCES for type deps)
3. For each related symbol, fetch signature-level info (declaration line, or class declaration + member names for types)
4. Format into structured sections
5. Each section includes the `full_name` so the LLM can drill deeper with `get_symbol_source()`

### Size Control

No explicit token budget in v1. Naturally bounded by one-hop traversal and signature-only rendering. If a method calls 50 methods, all 50 signatures are included. Add `max_callees` parameter later if needed.

---

## Cross-Cutting Concerns

### Incremental Re-indexing

When `reindex_file()` fires via watcher:

1. Delete the file node and all descendants (existing behavior)
2. Re-run Phase 1 structural indexing (existing behavior)
3. Run `SymbolResolver` for the single file — resolves both CALLS and REFERENCES edges

Watcher holds a reference to `SymbolResolver` (LSP already kept alive).

### Backward Compatibility

- Nodes without `end_line` degrade gracefully (tools return "re-index required")
- `get_context_for()` requires `end_line` — returns a clear message if re-indexing needed
- No formal migration. Re-indexing overwrites nodes with new properties.

### Error Handling

- `get_symbol_source()`: file not found → clear error. Symbol not in graph → clear error.
- `SymbolResolver`: LSP fails to resolve a type → skip silently, log at debug level.
- `get_context_for()`: unresolved/external types → include `full_name` with a note.

### Testing

- **Unit tests** for `TypeRefExtractor` with C# code snippets (same pattern as `TreeSitterCallExtractor` tests)
- **Unit tests** for `get_context_for()` query composition with mocked graph data
- **Unit tests** for `get_symbol_source()` with mocked file reads
- **Integration tests** for `SymbolResolver` end-to-end (requires FalkorDB + .NET)
