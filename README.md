# Synapse

**Give your AI agent a deep understanding of your codebase — not just files and symbols, but the relationships between them.**

Synapse is an MCP server and CLI that builds a queryable graph of your codebase using Language Server Protocol analysis. It indexes symbols, call chains, inheritance trees, interface implementations, and type dependencies across C#, Python, TypeScript/JavaScript, and Java projects — then lets AI agents (or humans) query that graph to make safer, faster, better-informed code changes.

> **Work in progress.** Synapse is under active development. APIs, CLI commands, and graph schema may change without notice.

## Why Synapse

AI agents working with code today rely on grep and file reads. That works for simple lookups, but falls apart when the question is *"what happens if I change this?"* — when the answer depends on call chains, interface dispatch, inheritance, and test coverage spanning dozens of files.

Synapse gives your agent a compiler-grade understanding of how code connects, without reading every file.

| Without Synapse | With Synapse |
|---|---|
| Grep for `.DoWork(` across the codebase, filter false positives manually | `find_callers("DoWork")` — precise results, including calls through interfaces |
| Read 5+ files to understand a method before editing | `get_context_for("X", scope="edit")` — source, callers, dependencies, and test coverage in one call |
| Hope you found every caller before refactoring | `analyze_change_impact("X")` — structured impact report with test coverage |
| Manually trace from a method to its API endpoint | `find_entry_points("X")` — automatic root-caller discovery |
| Guess which tests cover a method | Impact analysis separates prod callers from test callers automatically |

## Key Features

### Deep Call Graph

Synapse uses a two-phase indexing approach: LSP extracts structural symbols (classes, methods, properties), then tree-sitter finds call sites and LSP resolves what each call points to. The result is a graph of CALLS edges between methods — not string matches, but semantically resolved references.

This means your agent can follow a method call through 6 levels of indirection and know exactly what code is reachable, without reading a single file.

**Tools:** `find_callers`, `find_callees`, `trace_call_chain`, `get_call_depth`, `find_entry_points`

### Interface Dispatch Resolution

In dependency-injected codebases, `service.Process()` could mean any of 5 concrete implementations. Grep finds the interface method. Synapse finds the interface method *and* every concrete implementation, automatically.

The graph models interface dispatch explicitly: `find_callers("IOrderService.Process")` returns callers of every class that implements `Process`, not just callers of the interface declaration.

**Tools:** `find_callers` (with `include_interface_dispatch`), `find_implementations`, `find_interface_contract`

### Impact Analysis

Before your agent changes a method, it should know: how many places call it, whether tests cover it, and what it depends on. `analyze_change_impact` answers all three in a single, token-efficient response — categorized into direct callers, transitive callers (2-4 hops), test coverage, and downstream callees.

**Tools:** `analyze_change_impact`, `find_type_impact`, `get_context_for` (with `scope="edit"`)

### Scoped Context

`get_context_for` is the recommended starting point for understanding any symbol. Instead of reading entire files, your agent gets exactly the context it needs:

- **`structure`** — type overview with member signatures (no method bodies)
- **`method`** — source code + interface contract + callees + dependencies
- **`edit`** — callers with line numbers, relevant dependencies, test coverage

The right scope means fewer tokens spent on context your agent won't use.

**Tools:** `get_context_for`

### Automatic Graph Sync

The graph stays fresh without manual intervention. When `auto_sync` is enabled (the default), every tool call checks whether the codebase has changed since the last index — using `git diff` for git repos, or file modification times otherwise — and re-indexes only the changed files.

For longer sessions, `watch_project` keeps the graph updated in real-time as files change on disk.

**Tools:** `sync_project`, `get_index_status`

### Token-Efficient Output

Synapse is designed for AI consumption. Outputs use shortened symbol references (`OrderService.Process` instead of `Com.Example.Services.OrderService.Process`), relative file paths, and compact text formats. Tools like `find_usages` and `analyze_change_impact` return structured Markdown summaries instead of raw JSON arrays, reducing token consumption while preserving all the information an agent needs to make decisions.

### Multi-Language, One Interface

C#, Python, TypeScript/JavaScript, and Java projects all use the same tools, the same graph schema, and the same query patterns. Each language has a plugin that handles LSP communication, call site extraction, import resolution, and type reference detection — but the agent doesn't need to know any of that. `find_callers` works the same whether the codebase is C# or Python.

### Multi-Project Isolation

Each project gets its own Memgraph instance via Docker, named deterministically from the project path. Index 10 projects simultaneously — queries from each directory hit the correct graph automatically. Containers persist across sessions and restart on demand.

## Prerequisites

- **Python 3.11+**
- **Docker** — Synapse automatically manages per-project Memgraph containers
- **.NET SDK** — required for C# projects (Roslyn language server)
- **Pyright** (`npm install -g pyright`) — required for Python projects
- **typescript-language-server** (`npm install -g typescript-language-server typescript`) — required for TypeScript/JavaScript projects

## How it works

When you run any Synapse command from a project directory, Synapse automatically:

1. Creates a `.synapse/config.json` in the project root with a deterministic container name and port
2. Starts a dedicated Memgraph Docker container for that project (or reuses an existing one)
3. Connects to the container's Bolt port for all graph operations

Each project's graph is fully isolated — indexing project A has no effect on project B. Containers are named `synapse-<hash>` based on the absolute project path, so they persist across sessions.

## Installation

```bash
pip install -e .
```

This installs two entry points:

- `synapse` — CLI
- `synapse-mcp` — MCP server

## MCP Server Setup

Add Synapse to your MCP client config (e.g. Claude Desktop's `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "synapse": {
      "command": "synapse-mcp"
    }
  }
}
```

The MCP server resolves the project from the current working directory at startup and connects to its Memgraph container automatically.

---

## CLI

```
synapse <command> [args]
```

### Project management

| Command | Description |
|---|---|
| `synapse index <path> [--language csharp\|python\|typescript]` | Index a project into the graph (auto-detects language if omitted) |
| `synapse watch <path>` | Watch a project for file changes and keep the graph updated (runs until Ctrl+C) |
| `synapse delete <path>` | Remove a project and all its graph data |
| `synapse status [path]` | Show index status for one project, or list all indexed projects |

### Graph queries

| Command | Description |
|---|---|
| `synapse symbol <full_name>` | Get a symbol's node and its relationships |
| `synapse source <full_name> [--include-class]` | Print the source code of a symbol |
| `synapse callers <method_full_name>` | Find all methods that call a given method |
| `synapse callees <method_full_name>` | Find all methods called by a given method |
| `synapse implementations <interface_name>` | Find all concrete implementations of an interface |
| `synapse hierarchy <class_name>` | Show the full inheritance chain for a class |
| `synapse search <query> [--kind <kind>]` | Search symbols by name, optionally filtered by kind (e.g. `method`, `class`) |
| `synapse type-refs <full_name>` | Find all symbols that reference a given type |
| `synapse dependencies <full_name>` | Find all types referenced by a given symbol |
| `synapse context <full_name>` | Get the full context needed to understand or modify a symbol |
| `synapse query <cypher>` | Execute a raw read-only Cypher query against the graph |

### Summaries

Summaries are free-text annotations attached to any symbol — useful for capturing architectural context that the graph alone doesn't convey.

| Command | Description |
|---|---|
| `synapse summary get <full_name>` | Get the summary for a symbol |
| `synapse summary set <full_name> <content>` | Set the summary for a symbol |
| `synapse summary list [--project <path>]` | List all symbols that have summaries |

### Examples

```bash
# Index a C# project
synapse index /path/to/csharp-project

# Index a Python project
synapse index /path/to/python-project

# Index a TypeScript project
synapse index /path/to/ts-project

# Find everything that calls a specific method
synapse callers "MyNamespace.MyClass.DoWork"

# Find all classes that implement an interface
synapse implementations "IOrderService"

# See the inheritance hierarchy of a class
synapse hierarchy "MyNamespace.BaseController"

# Search for all methods containing "Payment"
synapse search "Payment" --kind method

# Get the source code for a method
synapse source "MyNamespace.MyClass.DoWork"

# Get all context needed to understand a symbol
synapse context "MyNamespace.MyClass"

# Watch for live updates while developing
synapse watch /path/to/my/project
```

---

## MCP Tools

These tools are available to any MCP client connected to `synapse-mcp`.

### Project management

| Tool | Parameters | Description |
|---|---|---|
| `index_project` | `path`, `language?` | Index a project (auto-detects language if omitted) |
| `sync_project` | `path` | Incremental sync — re-indexes only changed files using git diff or mtime |
| `list_projects` | — | List all indexed projects with metadata |
| `delete_project` | `path` | Remove a project and all its graph data |
| `get_index_status` | `path` | File count, symbol count, per-label breakdown |

### Symbol discovery

| Tool | Parameters | Description |
|---|---|---|
| `search_symbols` | `query`, `kind?`, `namespace?`, `file_path?`, `language?` | Find symbols by name with optional filters |
| `get_symbol` | `full_name` | Get a symbol's node properties and relationships |
| `get_symbol_source` | `full_name`, `include_class_signature?` | Get the source code of a symbol from disk |
| `find_implementations` | `interface_name` | Find all concrete implementations of an interface |
| `get_hierarchy` | `class_name` | Full inheritance chain: parents, children, implemented interfaces |

### Call graph

| Tool | Parameters | Description |
|---|---|---|
| `find_callers` | `method`, `include_interface_dispatch?`, `exclude_test_callers?` | Find all callers of a method, including through interface dispatch |
| `find_callees` | `method`, `include_interface_dispatch?` | Find all methods called by a given method |
| `find_usages` | `full_name`, `exclude_test_callers?`, `limit?` | Unified usage lookup — auto-selects strategy by symbol kind |
| `trace_call_chain` | `start`, `end`, `max_depth?` | Find all call paths between two methods |
| `find_entry_points` | `method`, `max_depth?`, `exclude_pattern?` | Find root callers (API/controller endpoints) that reach a method |
| `get_call_depth` | `method`, `depth?` | Get all methods reachable from a starting point up to N levels deep |
| `find_interface_contract` | `method` | Find the interface a method satisfies and all sibling implementations |

### Impact analysis

| Tool | Parameters | Description |
|---|---|---|
| `get_context_for` | `full_name`, `scope?`, `max_lines?` | Context for understanding or editing a symbol (scopes: `structure`, `method`, `edit`) |
| `analyze_change_impact` | `method` | What breaks if you change this? Direct callers, transitive callers, test coverage, callees |
| `find_type_references` | `full_name`, `kind?` | Find all symbols that reference a type (as parameter, return type, or field) |
| `find_type_impact` | `type_name`, `limit?` | All code referencing a type, categorized as prod or test |
| `find_dependencies` | `full_name`, `depth?`, `limit?` | Field-type dependencies of a symbol, with optional transitive traversal |

### Summaries

| Tool | Parameters | Description |
|---|---|---|
| `set_summary` | `full_name`, `content` | Attach a free-text summary to a symbol |
| `get_summary` | `full_name` | Retrieve the summary for a symbol |
| `list_summarized` | `project_path?` | List all symbols that have summaries |
| `summarize_from_graph` | `class_name` | Auto-generate a structural summary from the graph |

### Raw queries

| Tool | Parameters | Description |
|---|---|---|
| `get_schema` | — | Return the full graph schema: labels, properties, relationships |
| `execute_query` | `cypher` | Execute a read-only Cypher query (mutating statements are blocked) |
| `audit_architecture` | `rule` | Run architectural audit rules (e.g. `layering_violations`, `untested_services`) |

---

## Graph model

### Node labels

Structural nodes (identified by `path`):

- `:Repository` — the indexed project root
- `:Directory` — a directory within the project
- `:File` — a source file

Symbol nodes (identified by `full_name`):

- `:Package` — a namespace or package
- `:Class` — classes, abstract classes, enums, and records (distinguished by the `kind` property)
- `:Interface` — interfaces
- `:Method` — methods (with `signature`, `is_abstract`, `is_static`, `line` properties)
- `:Property` — properties (with `type_name`)
- `:Field` — fields (with `type_name`)

A `:Summarized` label is added to any node that has a user-attached summary.

### Relationships

- `CONTAINS` — structural containment: Repository→Directory, Directory→File, File→Symbol, and Class/Package→nested symbols
- `IMPORTS` — file imports a package/namespace
- `CALLS` — method calls another method (with optional `call_sites` property for line/column tracking)
- `OVERRIDES` — method overrides a base method
- `IMPLEMENTS` — class implements an interface; also used at method level for interface method→concrete implementation
- `DISPATCHES_TO` — interface method→concrete implementation (inverse of method-level IMPLEMENTS, used for call graph traversal)
- `INHERITS` — class inherits from another class, or interface extends another interface
- `REFERENCES` — symbol references a type (field type, parameter type, return type)

Fully-qualified names (e.g. `MyNamespace.MyClass.DoWork`) are used as symbol identifiers throughout.

---

## Multi-project usage

Synapse manages Docker containers automatically. Each project directory you work in gets its own isolated Memgraph instance:

```bash
# Index two different projects — each gets its own container
cd /path/to/project-a && synapse index .
cd /path/to/project-b && synapse index .

# Queries from each directory hit the correct graph
cd /path/to/project-a && synapse search "Controller"  # searches project A's graph
cd /path/to/project-b && synapse search "Controller"  # searches project B's graph
```

Container and port configuration is stored in `.synapse/config.json` in each project root. Add `.synapse/` to your `.gitignore`.

Containers persist across sessions. If a container was stopped, Synapse automatically restarts it on the next command. To clean up:

```bash
# Containers can be managed with standard Docker commands
docker ps --filter "name=synapse-"     # list Synapse containers
docker stop synapse-abc123def456       # stop a specific container
docker rm synapse-abc123def456         # remove a specific container
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run unit tests (no Docker, Memgraph, or .NET required)
pytest tests/unit/

# Run integration tests (requires Docker + Memgraph on localhost:7687 and .NET SDK)
docker compose up -d
pytest tests/integration/ -m integration
```

## AI Agent Configuration

Synapse automatically provides usage instructions to any MCP-compliant client via the protocol — most AI agents will make good tool choices out of the box.

The snippets below are **optional** additions for your AI platform's rules/instructions file. They provide platform-specific optimizations that go beyond what the MCP protocol delivers.

<details>
<summary><strong>Claude Code / Claude Desktop</strong> — add to your project's <code>CLAUDE.md</code></summary>

```markdown
## Synapse MCP

This project is indexed by the Synapse MCP server. Use it instead of grep/read for navigating code relationships:

- Before modifying a method, use `get_context_for` (scope="edit") to understand its callers, callees, dependencies, and test coverage
- Use `find_callers` / `find_usages` to trace how a symbol is used across the codebase — prefer this over grep
- Use `find_callees` or `get_call_depth` to understand what a method depends on downstream
- After making changes, use `analyze_change_impact` to verify no unexpected breakage
- Use `get_hierarchy` to understand inheritance before modifying class structures
- Use `search_symbols` to find symbols by name, kind, file, or namespace — faster and more precise than file search
- Use `execute_query` for ad-hoc Cypher queries; call `get_schema` first to see available labels and relationships
- Synapse tools appear as `mcp__synapse__<tool_name>` (e.g., `mcp__synapse__get_context_for`)
- Prefer Synapse tools over grep and Read for navigating code structure and call relationships
- Parallelize independent Synapse calls when possible (e.g., `find_callers` and `find_callees` for different methods)
```

</details>

<details>
<summary><strong>Cursor</strong> — save as <code>.cursor/rules/synapse.mdc</code></summary>

```markdown
---
description: Rules for using the Synapse MCP code intelligence server
globs:
alwaysApply: true
---

# Synapse MCP

Use Synapse MCP tools for all code navigation and understanding tasks. Do not use grep or file reads when a Synapse tool can answer the question.

## Before editing code
- Call get_context_for with scope="edit" to see callers, dependencies, and test coverage

## Finding code
- search_symbols to find symbols by name (supports kind, namespace, file_path, language filters)
- find_implementations to find classes implementing an interface
- get_hierarchy to understand inheritance chains

## Understanding call relationships
- find_callers to find who calls a method (includes interface dispatch automatically)
- find_callees to find what a method calls
- find_usages for unified lookup (auto-selects strategy by symbol kind)
- trace_call_chain to find paths between two methods
- find_entry_points to find API/controller entry points that reach a method

## Impact analysis
- analyze_change_impact before and after changes
- find_type_impact to find code affected by type shape changes
- find_dependencies for constructor/field type dependencies

## Reading code
- get_symbol_source for source code of a specific symbol
- get_context_for for source code plus relationships in one call

## Raw queries
- Call get_schema before writing Cypher
- execute_query is a last resort — use dedicated tools when possible
```

</details>

<details>
<summary><strong>Windsurf</strong> — add to <code>.windsurfrules</code></summary>

```markdown
# Synapse MCP

Use Synapse MCP tools for code navigation instead of grep or file reads.

Key tools by task:
- Before editing: get_context_for(scope="edit") for callers, deps, tests
- Find symbols: search_symbols (with kind/namespace/file_path filters)
- Who calls a method: find_callers (includes interface dispatch)
- What a method calls: find_callees
- All usages: find_usages (auto-selects by symbol kind)
- Implementations: find_implementations
- Inheritance: get_hierarchy
- Call paths: trace_call_chain
- Entry points: find_entry_points
- Impact analysis: analyze_change_impact
- Source code: get_symbol_source, or get_context_for for code + relationships
- Dependencies: find_dependencies
- Raw Cypher: get_schema first, then execute_query (last resort)

Avoid guessing symbol names — use search_symbols to discover them.
```

</details>

<details>
<summary><strong>GitHub Copilot</strong> — add to <code>.github/copilot-instructions.md</code></summary>

```markdown
# Synapse MCP

This project has a Synapse MCP server providing code intelligence tools. Use these tools proactively for code navigation — they are faster and more accurate than grep or file reads for understanding code structure.

## Essential workflow
1. Use `search_symbols` to find symbols by name (don't guess fully-qualified names)
2. Use `get_context_for` with `scope="edit"` before modifying any method
3. Use `analyze_change_impact` after making changes to verify safety

## Tool selection
- Callers of a method: `find_callers` (not raw Cypher)
- Callees of a method: `find_callees`
- All usages of any symbol: `find_usages`
- Interface implementations: `find_implementations`
- Inheritance chain: `get_hierarchy`
- Source code: `get_symbol_source`
- Full context: `get_context_for`
- Call paths: `trace_call_chain`
- Entry points: `find_entry_points`
- Dependencies: `find_dependencies`
- Raw Cypher: `get_schema` then `execute_query` (last resort)
```

</details>

<details>
<summary><strong>Generic / Other MCP Clients</strong></summary>

```text
Synapse MCP — Code Intelligence Tools

Use Synapse tools instead of grep/file reads for code navigation.

Before editing code:
  get_context_for(full_name, scope="edit") — shows callers, deps, tests

Finding symbols:
  search_symbols(query, kind, namespace, file_path) — discover by name

Call relationships:
  find_callers(method) — who calls this (includes interface dispatch)
  find_callees(method) — what this calls
  find_usages(symbol) — unified lookup, auto-selects by kind
  trace_call_chain(start, end) — paths between two methods
  find_entry_points(method) — API/controller roots

Structure:
  find_implementations(interface) — concrete implementors
  get_hierarchy(class) — inheritance chain
  find_dependencies(symbol) — field/constructor dependencies

Reading code:
  get_symbol_source(full_name) — source code
  get_context_for(full_name) — source + relationships

Impact analysis:
  analyze_change_impact(method) — callers, tests, callees

Raw queries (last resort):
  get_schema() — read schema first
  execute_query(cypher) — read-only Cypher

Don't guess symbol names — use search_symbols to discover them.
Don't use execute_query when a dedicated tool exists.
```

</details>
