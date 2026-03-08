# CLI & MCP Fix Design

**Date:** 2026-03-08

## Problem

Most CLI commands return empty output or unrenderable objects when given valid arguments. Root causes:

1. The service layer returns raw FalkorDB `Node` objects rather than plain dicts. The CLI cannot format them and the MCP cannot JSON-serialize them.
2. Commands that require a specific symbol kind (`callers`/`callees` need a Method, `implementations` needs an Interface) silently return nothing when given the wrong kind.
3. `index-calls` is a vestigial command — `index` already runs both phases.

## Approach

Fix at the service layer. Normalize all return values to plain `dict` using the existing `_p()` helper at every service method return boundary. This fixes both CLI rendering and MCP JSON serialization in one place.

## Design

### 1. Service Layer Normalization

Apply `_p()` at the return site of every method that currently returns FalkorDB Node objects:

- `get_symbol` → `dict | None`
- `find_implementations`, `find_callers`, `find_callees`, `search_symbols`, `list_projects`, `list_summarized` → `list[dict]`
- `find_type_references` → `list[dict]` with `"symbol"` value unwrapped via `_p()`
- `find_dependencies` → `list[dict]` with `"type"` value unwrapped via `_p()`
- `get_hierarchy` → `{"parents": list[dict], "children": list[dict]}`
- `get_index_status` — already returns plain scalars, no change

`_p()` remains a private helper in `service.py`. No new module.

### 2. CLI Formatting

Each list command prints one entry per line in human-readable form:

| Command | Format |
|---|---|
| `callers`, `callees`, `implementations`, `search` | `full_name — signature` (methods); `full_name` (types) |
| `hierarchy` | Two labeled sections: `Parents:` and `Children:` with `full_name` per line |
| `type-refs`, `dependencies` | `full_name (kind)` per line |
| Empty results | Print `"No results."` |

**Semantic validation** — checked via `get_symbol` before calling the service:

| Command | Required label | Error |
|---|---|---|
| `callers`, `callees` | `Method` | `"'X' is a <kind>, not a Method. Try a specific method like 'X.MethodName'."` |
| `implementations` | `Interface` | `"'X' is a <kind>. To find what interfaces it implements, use: synapse hierarchy X"` |

**Removed:** `index-calls` command.

**Unchanged:** `watch`, `summary` subcommands.

### 3. MCP Layer

No changes to `tools.py`. Service normalization makes all return values JSON-serializable for free.

## Out of Scope

- Partial/short-name matching (user must pass fully qualified names)
- Output format changes to the MCP tools
- New CLI commands
