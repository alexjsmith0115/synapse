<p align="center">
  <img src="synapse-logo.svg" alt="Synapse" width="300">
</p>

# Synapse

[![CI](https://github.com/alexjsmith0115/synapse/actions/workflows/ci.yml/badge.svg)](https://github.com/alexjsmith0115/synapse/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Give your AI agent a deep understanding of your codebase — not just files and symbols, but the relationships between them.**

Synapse is an MCP server and CLI that builds a queryable graph of your codebase using Language Server Protocol analysis. It indexes symbols, call chains, inheritance trees, interface implementations, and type dependencies across C#, Python, TypeScript/JavaScript, and Java projects — then lets AI agents (or humans) query that graph to make safer, faster, better-informed code changes.

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

**Tools:** `find_callers`, `find_callees` (with `depth` for call trees), `trace_call_chain`, `find_entry_points`

### Interface Dispatch Resolution

In dependency-injected codebases, `service.Process()` could mean any of 5 concrete implementations. Grep finds the interface method. Synapse finds the interface method *and* every concrete implementation, automatically.

The graph models interface dispatch explicitly: `find_callers("IOrderService.Process")` returns callers of every class that implements `Process`, not just callers of the interface declaration.

**Tools:** `find_callers` (with `include_interface_dispatch`), `find_implementations` | **CLI:** `contract`

### Impact Analysis

Before your agent changes a method, it should know: how many places call it, whether tests cover it, and what it depends on. `analyze_change_impact` answers all three in a single, token-efficient response — categorized into direct callers, transitive callers (2-4 hops), test coverage, and downstream callees.

**Tools:** `analyze_change_impact`, `find_usages` (with `include_test_breakdown`), `get_context_for` (with `scope="edit"`)

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

**Tools:** `sync_project`, `list_projects` (with `path` for index status)

### Token-Efficient Output

Synapse is designed for AI consumption. Outputs use shortened symbol references (`OrderService.Process` instead of `Com.Example.Services.OrderService.Process`), relative file paths, and compact text formats. Tools like `find_usages` and `analyze_change_impact` return structured Markdown summaries instead of raw JSON arrays, reducing token consumption while preserving all the information an agent needs to make decisions.

### Multi-Language, One Interface

C#, Python, TypeScript/JavaScript, and Java projects all use the same tools, the same graph schema, and the same query patterns. Each language has a plugin that handles LSP communication, call site extraction, import resolution, and type reference detection — but the agent doesn't need to know any of that. `find_callers` works the same whether the codebase is C# or Python.

### HTTP Endpoint Tracing

In full-stack projects with a backend API and a frontend client, Synapse traces HTTP dependencies across the language boundary. It detects server-side endpoint definitions and client-side HTTP calls, matches them by route pattern, and links them through shared `Endpoint` nodes in the graph.

**Supported Frameworks:**

| Language | Server Frameworks | Client Libraries |
|----------|------------------|-----------------|
| C# | ASP.NET Core (`[ApiController]`, `[Route]`, `[HttpGet/Post/Put/Delete]`) | -- |
| TypeScript / JavaScript | Express, NestJS | axios, fetch (template literals, constant references) |
| Python | Flask, Django, FastAPI | requests, httpx, urllib |
| Java | Spring Boot (`@RequestMapping`, `@GetMapping`, etc.), JAX-RS (`@Path`, `@GET`) | -- |

Route matching handles parameterized paths (`{id}` on either side) and common base URL prefixes (`/api`, `/api/v1`).

**MCP Tools:**

Use `find_http_endpoints` to search for endpoints by route pattern, HTTP method, or language:

```json
{ "tool": "find_http_endpoints", "arguments": { "route": "items", "http_method": "GET" } }
```

Use `trace_http_dependency` to find the server handler and all client call sites for a specific endpoint:

```json
{ "tool": "trace_http_dependency", "arguments": { "route": "/api/items", "http_method": "GET" } }
```

Each result includes a `has_server_handler` field that is `false` for client calls to unindexed or external services.

**Known Limitations:**

- **Dynamic URL construction** -- URLs assembled at runtime (e.g., string concatenation, builder patterns) cannot be resolved by static analysis.
- **API gateway / middleware rewrites** -- Route rewrites applied by API gateways, reverse proxies, or middleware are invisible to source-level analysis. The traced routes reflect what the source code declares, not what reaches the network.

### Container Management

Synapse uses Memgraph as its graph database, managed via Docker. By default, all projects share a single container for simplicity. You can opt into per-project containers when isolation is needed.

| Mode | When | Container | Config |
|---|---|---|---|
| **Shared** (default) | Most users | One `synapse-shared` container on port 7687 | `~/.synapse/config.json` |
| **Dedicated** (opt-in) | Need per-project isolation | One container per project, dynamic port | `.synapse/config.json` in project root |
| **External** | BYO Memgraph | No container — connects directly | `~/.synapse/config.json` |

## Supported Languages

| Language | File Extensions | Language Server |
|---|---|---|
| C# | `.cs` | Roslyn Language Server |
| Python | `.py` | Pyright |
| TypeScript / JavaScript | `.ts`, `.tsx`, `.js`, `.jsx`, `.mts`, `.cts`, `.mjs`, `.cjs` | typescript-language-server |
| Java | `.java` | Eclipse JDTLS |

All languages use the same tools, graph schema, and query patterns. Language detection is automatic based on file extensions, or can be specified explicitly with `--language`.

## Prerequisites

- **Python 3.11+**
- **Docker** — Synapse auto-manages a shared Memgraph container (or per-project containers if opted in). Not required when connecting to an external Memgraph instance.
- **.NET SDK** — required for C# projects (Roslyn Language Server is auto-downloaded on first index)
- **Pyright** (`npm install -g pyright`) — required for Python projects
- **typescript-language-server** (`npm install -g typescript-language-server typescript`) — required for TypeScript/JavaScript projects

Run `synapse doctor` to check your environment.

## How it works

When you run any Synapse command from a project directory, Synapse automatically:

1. Connects to the shared Memgraph container (starting it if needed), or provisions a dedicated container if the project opts in
2. Creates graph nodes scoped to the project path — multiple projects coexist in the same database, identified by their `Repository` node
3. Indexes symbols via LSP and call sites via tree-sitter, writing nodes and edges to the graph

Global config lives at `~/.synapse/config.json`. Per-project config (`.synapse/config.json`) is only created when using dedicated containers. Add `.synapse/` to your `.gitignore`.

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

### Environment

| Command | Description |
|---|---|
| `synapse doctor` | Check environment: Docker, Memgraph, and all language server dependencies |

### Project management

| Command | Description |
|---|---|
| `synapse index <path> [--language <lang>]` | Index a project (auto-detects language if omitted) |
| `synapse sync <path>` | Sync the graph with the current filesystem — re-indexes only changed files |
| `synapse watch <path>` | Watch a project for file changes and keep the graph updated (runs until Ctrl+C) |
| `synapse delete <path>` | Remove a project and all its graph data |
| `synapse status [path]` | Show index status for one project, or list all indexed projects |

### Graph queries

| Command | Description |
|---|---|
| `synapse symbol <full_name>` | Get a symbol's node and its relationships |
| `synapse source <full_name> [--include-class]` | Print the source code of a symbol |
| `synapse search <query> [--kind <kind>] [--language/-l <lang>]` | Search symbols by name, optionally filtered by kind or language |
| `synapse callers <method> [--include-tests] [--tree/-t]` | Find all methods that call a given method |
| `synapse callees <method> [--tree/-t]` | Find all methods called by a given method |
| `synapse call-depth <method> [--depth/-d <n>] [--tree/-t]` | Show all methods reachable from a method up to N levels |
| `synapse implementations <interface>` | Find all concrete implementations of an interface or abstract class |
| `synapse hierarchy <class> [--tree/-t]` | Show the full inheritance chain for a class |
| `synapse contract <method>` | Find the interface contract and sibling implementations for a method |
| `synapse usages <full_name> [--include-tests]` | Find all code that uses a symbol (callers + type references) |
| `synapse type-refs <full_name> [--kind/-k <kind>]` | Find all symbols that reference a type (filter: `parameter`, `return_type`, `property_type`) |
| `synapse dependencies <full_name> [--tree/-t]` | Find all types referenced by a symbol |
| `synapse context <full_name> [--scope <scope>] [--max-lines <n>]` | Get context for understanding or modifying a symbol (scopes: `structure`, `method`, `edit`) |
| `synapse trace <start> <end> [--depth/-d <n>] [--tree/-t]` | Trace call paths between two methods |
| `synapse entry-points <method> [--depth/-d <n>] [--include-tests] [--tree/-t]` | Find all entry points (API/controller roots) that reach a method |
| `synapse impact <method>` | Analyze the blast radius of changing a method |
| `synapse type-impact <type_name>` | Find all code affected if a type changes shape |
| `synapse audit <rule>` | Run an architectural audit rule (`layering_violations`, `untested_services`) |
| `synapse query <cypher>` | Execute a raw read-only Cypher query against the graph |

### Summaries

Summaries let you attach non-derivable context to symbols — design rationale, constraints, ownership, deprecation plans. Don't use them for structural descriptions (interfaces, dependencies, method counts) — that information is already queryable live via `get_context_for`, `find_dependencies`, etc.

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
synapse hierarchy "MyNamespace.BaseController" --tree

# Search for all methods containing "Payment"
synapse search "Payment" --kind method

# Get the source code for a method
synapse source "MyNamespace.MyClass.DoWork"

# Get all context needed to edit a symbol
synapse context "MyNamespace.MyClass" --scope edit

# Show methods reachable up to 4 levels deep
synapse call-depth "MyNamespace.MyClass.DoWork" --depth 4 --tree

# Trace how one method reaches another
synapse trace "Controller.Handle" "Repository.Save" --tree

# Analyze impact before making a change
synapse impact "MyNamespace.MyClass.DoWork"

# Watch for live updates while developing
synapse watch /path/to/my/project

# Check environment setup
synapse doctor
```

---

## MCP Tools

These tools are available to any MCP client connected to `synapse-mcp`. There are 19 tools organized into 6 categories.

### Project management

| Tool | Parameters | Description |
|---|---|---|
| `index_project` | `path`, `language?` | Index a project (auto-detects language if omitted) |
| `list_projects` | `path?` | List all indexed projects. When `path` is provided, returns detailed index status (file count, symbol count, per-label breakdown) instead |
| `sync_project` | `path` | Incremental sync — re-indexes only changed files using git diff or mtime |

### Symbol discovery

| Tool | Parameters | Description |
|---|---|---|
| `search_symbols` | `query`, `kind?`, `namespace?`, `file_path?`, `language?`, `limit?` | Find symbols by name substring with optional filters |
| `get_symbol` | `full_name` | Get a symbol's metadata (file path, line range, kind). Does not return source code |
| `get_symbol_source` | `full_name`, `include_class_signature?` | Get the source code of a symbol from disk |
| `find_implementations` | `interface_name`, `limit?` | Find all concrete implementations of an interface |
| `get_hierarchy` | `class_name` | Full inheritance chain: parents, children, implemented interfaces |

### Call graph

| Tool | Parameters | Description |
|---|---|---|
| `find_callers` | `method_full_name`, `include_interface_dispatch?`, `exclude_test_callers?`, `limit?` | Find all callers of a method, including through interface dispatch |
| `find_callees` | `method_full_name`, `include_interface_dispatch?`, `limit?`, `depth?` | Find all methods called by a given method. When `depth` is set, returns all reachable methods up to N levels (call tree mode) |
| `find_usages` | `full_name`, `exclude_test_callers?`, `limit?`, `kind?`, `include_test_breakdown?` | Unified usage lookup — auto-selects strategy by symbol kind. Use `kind` to filter type references (`parameter`, `return_type`, `property_type`). Use `include_test_breakdown` for prod/test categorized impact |
| `trace_call_chain` | `start`, `end`, `max_depth?` | Find all call paths between two methods |
| `find_entry_points` | `method`, `max_depth?`, `exclude_pattern?`, `exclude_test_callers?` | Find root callers (API/controller endpoints) that reach a method |

### Impact analysis

| Tool | Parameters | Description |
|---|---|---|
| `get_context_for` | `full_name`, `scope?`, `max_lines?` | Context for understanding or editing a symbol (scopes: `structure`, `method`, `edit`) |
| `analyze_change_impact` | `method` | What breaks if you change this? Direct callers, transitive callers, test coverage, callees |
| `find_dependencies` | `full_name`, `depth?`, `limit?` | Field-type dependencies of a symbol, with optional transitive traversal |

### Summaries

| Tool | Parameters | Description |
|---|---|---|
| `summary` | `action` (`set`/`get`/`list`), `full_name?`, `content?`, `project_path?` | Persist non-derivable context on a symbol (design rationale, constraints, ownership) |

### Raw queries

| Tool | Parameters | Description |
|---|---|---|
| `get_schema` | — | Return the full graph schema: labels, properties, relationships |
| `execute_query` | `cypher` | Execute a read-only Cypher query (mutating statements are blocked) |

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

A `:Summarized` label is added to any node that has an attached summary (non-derivable context like design rationale or constraints).

When HTTP endpoint extraction is enabled:

- `:Endpoint` — an HTTP endpoint (with `route`, `http_method`, `name` properties)

### Relationships

- `CONTAINS` — structural containment: Repository→Directory, Directory→File, File→Symbol, and Class/Package→nested symbols
- `IMPORTS` — file imports a package/namespace
- `CALLS` — method calls another method (with optional `call_sites` property for line/column tracking)
- `OVERRIDES` — method overrides a base method
- `IMPLEMENTS` — class implements an interface; also used at method level for interface method→concrete implementation
- `DISPATCHES_TO` — interface method→concrete implementation (inverse of method-level IMPLEMENTS, used for call graph traversal)
- `INHERITS` — class inherits from another class, or interface extends another interface
- `REFERENCES` — symbol references a type (field type, parameter type, return type)

When HTTP endpoint extraction is enabled:

- `SERVES` — method handles an HTTP endpoint (controller action → Endpoint)
- `HTTP_CALLS` — method makes an HTTP request to an endpoint (frontend service → Endpoint, with `call_sites`)

Fully-qualified names (e.g. `MyNamespace.MyClass.DoWork`) are used as symbol identifiers throughout.

---

## Multi-project usage

By default, all projects share a single Memgraph container (`synapse-shared` on port 7687). Each project's data is scoped by its `Repository` node in the graph — indexing project A has no effect on project B.

```bash
# Index two different projects — both use the shared container
cd /path/to/project-a && synapse index .
cd /path/to/project-b && synapse index .

# Queries from each directory are scoped to that project's graph data
cd /path/to/project-a && synapse search "Controller"  # searches project A's graph
cd /path/to/project-b && synapse search "Controller"  # searches project B's graph
```

### Dedicated containers (opt-in)

If you need full container isolation (e.g. for resource management or data separation), add `"dedicated_instance": true` to the project's `.synapse/config.json`:

```json
{
  "dedicated_instance": true
}
```

Synapse will provision a per-project container (`synapse-<project-name>`) on a dynamically allocated port. Container and port details are stored in `.synapse/config.json` in the project root.

### External Memgraph

To connect to an existing Memgraph instance instead of using Docker, set the connection in `~/.synapse/config.json`:

```json
{
  "external_host": "memgraph.example.com",
  "external_port": 7687
}
```

Docker is not required in external mode.

### Managing containers

```bash
# List Synapse containers
docker ps --filter "name=synapse-"

# Stop the shared container
docker stop synapse-shared

# Stop and remove a dedicated container
docker stop synapse-myproject
docker rm synapse-myproject
```

Containers persist across sessions. If a container was stopped, Synapse automatically restarts it on the next command.

## Ignoring Files (`.synignore`)

Place a `.synignore` file in your project root to exclude directories or files from indexing. It uses `.gitignore` syntax:

```gitignore
# Directories to skip entirely
worktrees/
generated/
vendor/

# File patterns
*.generated.cs
**/test_data/**
```

Patterns are applied during file discovery, file watching, and git-based sync — ignored paths are never indexed or re-indexed. Without a `.synignore` file, Synapse uses its built-in exclusion list (`.git`, `node_modules`, `__pycache__`, `dist`, `build`, etc.).

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

The snippets below are **optional** additions for your AI platform's rules/instructions file. They reinforce tool selection patterns and add platform-specific guidance that goes beyond what the MCP protocol delivers.

<details>
<summary><strong>Claude Code / Claude Desktop</strong> — add to your project's <code>CLAUDE.md</code></summary>

```markdown
## Synapse MCP

This project is indexed by the Synapse MCP server. Use it instead of grep/read for navigating code relationships:

### Workflow
- Projects must be indexed before querying. Use `list_projects` to check what's indexed, `index_project` to index, `sync_project` to refresh a stale index.
- If queries return empty results, use `list_projects(path=...)` to check whether the project is indexed.

### Tool selection (by task)
- Before modifying a method, use `get_context_for` with scope="edit" to understand its callers, callees, dependencies, and test coverage
- Use `find_callers` / `find_usages` to trace how a symbol is used across the codebase — prefer this over grep
- Use `find_callees` (with optional `depth` param for reachable call tree) to understand what a method depends on downstream
- Read source code of a symbol with `get_symbol_source` (not by reading files by line range)
- Full context (source + relationships) in one call: `get_context_for` (not get_symbol + get_symbol_source + find_callers separately)
- Find a symbol by name: `search_symbols` (not guessing full_name strings) — supports kind, namespace, file_path, language filters
- All usages of any symbol: `find_usages` (auto-selects strategy by symbol kind). Use `kind` param to filter type references, `include_test_breakdown=True` for prod/test split
- After making changes, use `analyze_change_impact` to verify no unexpected breakage
- Trace call paths between two methods: `trace_call_chain`
- Find API/controller entry points that reach a method: `find_entry_points`
- Find all classes implementing an interface: `find_implementations`
- Use `get_hierarchy` to understand inheritance before modifying class structures
- Find constructor/field dependencies: `find_dependencies` (with optional `depth` for transitive)
- Annotate symbols with non-derivable context (design rationale, constraints, ownership): `summary` with action='set'/'get'/'list'
- Use `execute_query` for ad-hoc Cypher queries; call `get_schema` first to see available labels and relationships

### Anti-patterns
- Do not use `execute_query` when a dedicated tool exists for the task
- Do not read files with grep or cat when `get_symbol_source` or `get_context_for` can retrieve the exact code
- Do not guess symbol names — use `search_symbols` to discover them first
- Do not skip `get_context_for` with scope="edit" before modifying a method

### Efficiency
- Use the `scope` parameter on `get_context_for` to control detail level: "structure" for overview, "method" for focused, "edit" for modification prep
- Use `search_symbols` with kind, namespace, or file_path filters to narrow results
- Parallelize independent Synapse calls when possible (e.g., `find_callers` and `find_callees` for different methods)
- Synapse tools appear as `mcp__synapse__<tool_name>` (e.g., `mcp__synapse__get_context_for`)

### CLI-only tools (not available via MCP)
- `synapse doctor` — check runtime environment and dependencies
- `synapse delete <path>` — delete a project and all its graph data
- `synapse status <path>` — detailed index status (also available via `list_projects(path=...)`)
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

## Workflow
- Projects must be indexed before querying. Use list_projects to check, index_project to index, sync_project to refresh.
- If queries return empty results, use list_projects(path=...) to verify the project is indexed.

## Before editing code
- Call get_context_for with scope="edit" to see callers, dependencies, and test coverage
- Do not skip this step — it shows what might break

## Finding symbols
- search_symbols to find symbols by name (supports kind, namespace, file_path, language filters)
- get_symbol for metadata (file path, line range, kind) without source code
- get_symbol_source for source code of a specific symbol
- find_implementations to find classes implementing an interface
- get_hierarchy to understand inheritance chains

## Understanding call relationships
- find_callers to find who calls a method (includes interface dispatch automatically)
- find_callees to find what a method calls (use depth param for full call tree)
- find_usages for unified lookup (auto-selects strategy by symbol kind; use kind param to filter type references, include_test_breakdown=True for prod/test split)
- trace_call_chain to find paths between two methods
- find_entry_points to find API/controller entry points that reach a method
- find_dependencies for constructor/field type dependencies (use depth for transitive)

## Impact analysis
- analyze_change_impact before and after changes
- find_usages with include_test_breakdown=True for prod/test categorized impact

## Annotations
- summary with action='set'/'get'/'list' to persist non-derivable context (design rationale, constraints, ownership) on symbols. Do not store structural descriptions — use get_context_for for that.

## Context scopes
- get_context_for(scope="structure") — type overview with member signatures, no method bodies
- get_context_for(scope="method") — source + interface contract + callees + dependencies
- get_context_for(scope="edit") — callers with line numbers, dependencies, test coverage

## Raw queries
- Call get_schema before writing Cypher
- execute_query is a last resort — use dedicated tools when possible

## Anti-patterns
- Do not use execute_query when a dedicated tool exists
- Do not read files with grep when get_symbol_source or get_context_for works
- Do not guess symbol names — use search_symbols to discover them first
```

</details>

<details>
<summary><strong>Windsurf</strong> — add to <code>.windsurfrules</code></summary>

```markdown
# Synapse MCP

Use Synapse MCP tools for code navigation instead of grep or file reads.

## Workflow
- Use list_projects to check what's indexed, index_project to index, sync_project to refresh.
- If queries return empty, use list_projects(path=...) to verify the project is indexed.

## Tool selection by task
- Before editing: get_context_for(scope="edit") for callers, deps, tests
- Find symbols: search_symbols (with kind/namespace/file_path/language filters)
- Symbol metadata: get_symbol (file path, line range, kind)
- Source code: get_symbol_source, or get_context_for for code + relationships
- Who calls a method: find_callers (includes interface dispatch)
- What a method calls: find_callees (use depth for call tree)
- All usages: find_usages (auto-selects by kind; use kind param for type refs, include_test_breakdown for prod/test split)
- Call paths: trace_call_chain
- Entry points: find_entry_points (API/controller roots)
- Implementations: find_implementations
- Inheritance: get_hierarchy
- Dependencies: find_dependencies (use depth for transitive)
- Impact analysis: analyze_change_impact
- Annotations: summary(action='set'/'get'/'list') for non-derivable context
- Raw Cypher: get_schema first, then execute_query (last resort)

## Context scopes
- "structure" — type overview, member signatures (no bodies)
- "method" — source + interface contract + callees + deps
- "edit" — callers with lines, deps, test coverage

## Anti-patterns
- Don't guess symbol names — use search_symbols to discover them
- Don't use execute_query when a dedicated tool exists
- Don't read files with grep when get_symbol_source or get_context_for works
```

</details>

<details>
<summary><strong>GitHub Copilot</strong> — add to <code>.github/copilot-instructions.md</code></summary>

```markdown
# Synapse MCP

This project has a Synapse MCP server providing code intelligence tools. Use these tools proactively for code navigation — they are faster and more accurate than grep or file reads for understanding code structure.

## Workflow
1. Projects must be indexed before querying. Use `list_projects` to check, `index_project` to index, `sync_project` to refresh.
2. If queries return empty results, use `list_projects(path=...)` to check whether the project is indexed.

## Essential workflow for edits
1. Use `search_symbols` to find symbols by name (don't guess fully-qualified names)
2. Use `get_context_for` with `scope="edit"` before modifying any method — it shows callers, dependencies, and tests that might break
3. Use `analyze_change_impact` after making changes to verify safety

## Tool selection
- Find symbols by name: `search_symbols` (supports kind, namespace, file_path, language filters)
- Symbol metadata: `get_symbol` (file path, line range, kind — no source code)
- Source code: `get_symbol_source` (or `get_context_for` for source + relationships)
- Callers of a method: `find_callers` (includes interface dispatch — not raw Cypher)
- Callees of a method: `find_callees` (use `depth` for full call tree)
- All usages of any symbol: `find_usages` (auto-selects by kind; use `kind` for type refs, `include_test_breakdown` for prod/test split)
- Interface implementations: `find_implementations`
- Inheritance chain: `get_hierarchy`
- Constructor/field dependencies: `find_dependencies` (use `depth` for transitive)
- Call paths between methods: `trace_call_chain`
- API/controller entry points: `find_entry_points`
- Impact analysis: `analyze_change_impact`
- Non-derivable annotations: `summary` (set/get/list — design rationale, constraints, ownership)
- Raw Cypher: `get_schema` then `execute_query` (last resort)

## Context scopes for get_context_for
- `"structure"` — type overview with member signatures (no bodies)
- `"method"` — source + interface contract + callees + dependencies
- `"edit"` — callers with line numbers, relevant dependencies, test coverage

## Anti-patterns
- Do not use `execute_query` when a dedicated tool exists
- Do not read files with grep when `get_symbol_source` or `get_context_for` works
- Do not guess symbol names — use `search_symbols` to discover them
```

</details>

<details>
<summary><strong>Generic / Other MCP Clients</strong></summary>

```text
Synapse MCP — Code Intelligence Tools (19 tools)

Use Synapse tools instead of grep/file reads for code navigation.

WORKFLOW:
  Projects must be indexed first. list_projects to check, index_project to
  index, sync_project to refresh. If queries return empty, check with
  list_projects(path=...).

BEFORE EDITING CODE:
  get_context_for(full_name, scope="edit") — callers, deps, test coverage

FINDING SYMBOLS:
  search_symbols(query, kind?, namespace?, file_path?, language?) — by name
  get_symbol(full_name) — metadata (file path, line range, kind)
  get_symbol_source(full_name) — source code from disk

CALL RELATIONSHIPS:
  find_callers(method) — who calls this (includes interface dispatch)
  find_callees(method, depth?) — what this calls (depth for call tree)
  find_usages(symbol, kind?, include_test_breakdown?) — unified lookup
  trace_call_chain(start, end) — paths between two methods
  find_entry_points(method) — API/controller roots

STRUCTURE:
  find_implementations(interface) — concrete implementors
  get_hierarchy(class) — inheritance chain
  find_dependencies(symbol, depth?) — field/constructor dependencies

IMPACT ANALYSIS:
  analyze_change_impact(method) — callers, transitive callers, tests, callees

ANNOTATIONS:
  summary(action='set'/'get'/'list') — persist non-derivable context
    (design rationale, constraints, ownership) on symbols

CONTEXT SCOPES (get_context_for):
  "structure" — type overview, member signatures (no bodies)
  "method"    — source + interface contract + callees + deps
  "edit"      — callers with lines, deps, test coverage

RAW QUERIES (last resort):
  get_schema() — read schema first
  execute_query(cypher) — read-only Cypher

AVOID:
  - Don't use execute_query when a dedicated tool exists
  - Don't read files with grep when get_symbol_source or get_context_for works
  - Don't guess symbol names — use search_symbols to discover them
  - Don't skip get_context_for(scope="edit") before modifying a method
```

</details>
