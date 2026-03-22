# Synapse

> **Work in progress.** Synapse is under active development. APIs, CLI commands, and graph schema may change without notice.

Synapse is an LSP-powered, Memgraph-backed tool that builds a queryable graph of your codebase. It indexes symbols, inheritance, interface implementations, method calls, and override relationships for C#, Python, and TypeScript/JavaScript projects, then exposes them via an MCP server (for AI assistants) and a CLI (for humans).

Each project gets its own isolated Memgraph instance via Docker — you can index multiple projects simultaneously and switch between them without re-indexing.

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
| `index_project` | `path: str`, `language: str = "csharp"` | Index a project into the graph (language: csharp, python, typescript) |
| `list_projects` | — | List all indexed projects |
| `delete_project` | `path: str` | Remove a project from the graph |
| `get_index_status` | `path: str` | Get the current index status for a project |
| `watch_project` | `path: str` | Start watching a project for file changes |
| `unwatch_project` | `path: str` | Stop watching a project |

### Graph queries

| Tool | Parameters | Description |
|---|---|---|
| `get_symbol` | `full_name: str` | Get a symbol's node and relationships by fully-qualified name |
| `get_symbol_source` | `full_name: str`, `include_class_signature: bool = False` | Get the source code of a symbol |
| `find_implementations` | `interface_name: str` | Find all concrete implementations of an interface |
| `find_callers` | `method_full_name: str` | Find all methods that call a given method |
| `find_callees` | `method_full_name: str` | Find all methods called by a given method |
| `get_hierarchy` | `class_name: str` | Get the full inheritance chain for a class |
| `search_symbols` | `query: str`, `kind: str \| None = None` | Search symbols by name, optionally filtered by kind |
| `find_type_references` | `full_name: str` | Find all symbols that reference a given type |
| `find_dependencies` | `full_name: str` | Find all types referenced by a given symbol |
| `get_context_for` | `full_name: str` | Get the full context needed to understand or modify a symbol |
| `execute_query` | `cypher: str` | Execute a read-only Cypher query (mutating statements are blocked) |

### Summaries

| Tool | Parameters | Description |
|---|---|---|
| `set_summary` | `full_name: str`, `content: str` | Attach a summary to a symbol |
| `get_summary` | `full_name: str` | Retrieve the summary for a symbol |
| `list_summarized` | `project_path: str \| None = None` | List all symbols that have summaries, optionally scoped to a project |

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
- `CALLS` — method calls another method
- `OVERRIDES` — method overrides a base method
- `IMPLEMENTS` — class implements an interface
- `INHERITS` — class inherits from another class, or interface extends another interface

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
