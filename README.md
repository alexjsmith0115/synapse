# Synapse

> **Work in progress.** Synapse is under active development. APIs, CLI commands, and graph schema may change without notice.

Synapse is an LSP-powered, FalkorDB-backed tool that builds a queryable graph of a C# codebase. It indexes symbols, inheritance, interface implementations, method calls, and override relationships, then exposes them via an MCP server (for AI assistants) and a CLI (for humans).

## Prerequisites

- **Python 3.11+**
- **FalkorDB** running on `localhost:6379` (default)
- **.NET SDK** — required for the C# language server to index projects

Start FalkorDB with Docker:

```bash
docker run -p 6379:6379 --rm falkordb/falkordb:latest
```

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

By default the server connects to FalkorDB at `localhost:6379`. There are no required environment variables.

---

## CLI

```
synapse <command> [args]
```

### Project management

| Command | Description |
|---|---|
| `synapse index <path> [--language csharp]` | Index a project into the graph |
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
synapse index /path/to/my/project

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
| `index_project` | `path: str`, `language: str = "csharp"` | Index a project into the graph |
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

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run unit tests (no FalkorDB or .NET required)
pytest tests/unit/

# Run integration tests (requires FalkorDB on localhost:6379 and .NET SDK)
pytest tests/integration/ -m integration
```
