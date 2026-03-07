# Synapse

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
| `synapse callers <method_full_name>` | Find all methods that call a given method |
| `synapse callees <method_full_name>` | Find all methods called by a given method |
| `synapse implementations <interface_name>` | Find all concrete implementations of an interface |
| `synapse hierarchy <class_name>` | Show the full inheritance chain for a class |
| `synapse search <query> [--kind <kind>]` | Search symbols by name, optionally filtered by kind (e.g. `method`, `class`) |
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
| `find_implementations` | `interface_name: str` | Find all concrete implementations of an interface |
| `find_callers` | `method_full_name: str` | Find all methods that call a given method |
| `find_callees` | `method_full_name: str` | Find all methods called by a given method |
| `get_hierarchy` | `class_name: str` | Get the full inheritance chain for a class |
| `search_symbols` | `query: str`, `kind: str \| None = None` | Search symbols by name, optionally filtered by kind |
| `execute_query` | `cypher: str` | Execute a read-only Cypher query (mutating statements are blocked) |

### Summaries

| Tool | Parameters | Description |
|---|---|---|
| `set_summary` | `full_name: str`, `content: str` | Attach a summary to a symbol |
| `get_summary` | `full_name: str` | Retrieve the summary for a symbol |
| `list_summarized` | `project_path: str \| None = None` | List all symbols that have summaries, optionally scoped to a project |

---

## Graph model

Symbols are stored as nodes with these labels:

- `:Method` — methods and functions
- `:Class` — classes, interfaces, abstract classes, enums, and records (distinguished by the `kind` property)

Relationships between nodes:

- `CALLS` — method calls another method
- `OVERRIDES` — method overrides a base method
- `IMPLEMENTS` — class implements an interface
- `INHERITS` — class inherits from another class

Fully-qualified names (e.g. `MyNamespace.MyClass.DoWork`) are used as node identifiers throughout.

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
