# Synapse Improvements Design

**Date:** 2026-03-09
**Scope:** Full pass — bug fixes, behavior improvements, documentation, nice-to-haves

---

## 1. Bug Fixes

### 1.1 `list_summarized` returns duplicates
`CONTAINS*` traversal produces one row per path to a summarized node. Fix: add `WITH DISTINCT n` after the `MATCH` in both query branches (project-scoped and global).

### 1.2 `search_symbols` kind filter error message
The `ValueError` currently gives no guidance. Fix: append the sorted list of valid values to the message. Also add `"Interface"` to `_VALID_KINDS` — it is a valid node label but currently excluded.

### 1.3 `get_symbol_source` stale error message
When source info is missing, the tool returns the same "Symbol not found" message as when the node doesn't exist. Fix: check node existence with `queries.get_symbol` first, then return one of three messages:
- Node missing → `"Symbol not found: {full_name}"`
- Node present, source missing → `"Source not available for {full_name} — re-index required"`
- Source present → return source (existing path)

---

## 2. Behavior Improvements

### 2.1 `find_callers` interface dispatch (#4)
Add `include_interface_dispatch: bool = True` to `queries.find_callers` and the MCP tool. When `True`, union two match arms:
1. Direct: `(caller)-[:CALLS]->(m {full_name: $full_name})`
2. Via interface: `(caller)-[:CALLS]->(iface_method)<-[:IMPLEMENTS]-(m {full_name: $full_name})`

Tool description note: *"By default, includes callers that invoke this method through an interface. Set include_interface_dispatch=False for direct CALLS edges only."*

### 2.2 `find_implementations` short name fallback (#5)
Two-phase query in `queries.find_implementations`: exact `full_name` match first; if empty, fall back to `WHERE n.full_name ENDS WITH ('.' + $name) OR n.full_name = $name`. MCP tool description notes both full and short names are accepted.

### 2.3 `get_hierarchy` includes interface implementations (#6)
Add a third query: `MATCH (c:Class {full_name: $full_name})-[:IMPLEMENTS]->(i:Interface) RETURN i`. Return shape: `{"parents": [...], "children": [...], "implements": [...]}`. `implements` is always present (empty list if none).

---

## 3. Documentation

### 3.1 New `get_schema` tool + inline schema in `execute_query` (#7)
New `get_schema` MCP tool returns a static dict:
- Node labels and their key properties
- Relationship types with source → target label
- Read-only constraint note

`execute_query` description gets a compact inline schema summary. `get_schema` is for when the AI needs the full picture before writing Cypher.

### 3.2 `search_symbols` kind values documented (#8)
Tool description explicitly lists all valid `kind` values.

### 3.3 `find_callers`/`find_callees` interface dispatch note (#9)
Both descriptions get: *"In C# codebases using DI, callers typically depend on interfaces. Use include_interface_dispatch=True (default) to include callers that dispatch through an interface."*

### 3.4 `get_context_for` output format documented (#10)
Tool description extended: explains the returned markdown contains symbol source (if available), direct dependency member signatures, and a re-index note if source is stale.

### 3.5 `watch_project`/`unwatch_project` purpose clarified (#11)
Both descriptions: *"Starts/stops a file watcher that automatically re-indexes changed .cs files. The watcher keeps the LSP process alive between changes. Use after index_project to keep the graph current during active development."*

---

## 4. Nice-to-Haves

### 4.1 `search_symbols` namespace + file filter (#12)
Add `namespace: str | None` and `file_path: str | None` optional params. Cypher conditions added dynamically:
- `namespace` → `AND n.full_name STARTS WITH $namespace`
- `file_path` → `AND n.file_path = $file_path`

Both combinable with existing `kind` filter.

### 4.2 `find_dependencies` depth parameter (#13)
Add `depth: int = 1` (max 5, capped to prevent runaway traversals). At depth > 1, use variable-length path: `MATCH (c {full_name: $full_name})-[:FIELD_TYPE*1..$depth]->(dep)`. Each result annotated with `depth` field (minimum distance from root). Tool description notes the cap.

---

## Affected Files

- `src/synapse/graph/queries.py` — all query changes
- `src/synapse/mcp/tools.py` — all tool description + behavior changes (new `get_schema` tool)
- `tests/unit/test_queries.py` — new/updated unit tests for each changed query
- `tests/unit/test_tools.py` — new/updated unit tests for tool-layer changes
