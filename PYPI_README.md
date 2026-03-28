# Synapse

Code intelligence MCP server — gives AI coding agents a queryable graph of your codebase.

## What it does

- Indexes C#, Python, TypeScript/JavaScript, and Java codebases using tree-sitter and Language Server Protocol
- Stores symbols, call chains, and relationships in a Memgraph graph database
- Exposes semantic query tools as MCP tools — AI agents can find callers, trace call chains, and analyze change impact without reading every file
- Supports incremental sync via git-diff-based change detection and live file watching

## Install

```
pip install synapse-mcp
docker compose up -d
```

The `docker compose up -d` command starts a local Memgraph instance (required for the graph database).

## Configure your MCP client

Add Synapse to your MCP client configuration (e.g., Claude Code `~/.claude.json`):

```json
{
  "mcpServers": {
    "synapse": {
      "command": "synapse-mcp"
    }
  }
}
```

Then index your project:

```
synapse index /path/to/your/project
```

## Supported Languages

- C#
- Python
- TypeScript / JavaScript
- Java

## Key MCP Tools

- `get_context_for` — full context for a symbol before editing (callers, callees, tests)
- `find_callers` — who calls a given method across the codebase
- `find_callees` — what a method depends on downstream
- `analyze_change_impact` — verify no unexpected breakage before committing
- `trace_call_chain` — find call paths between two methods
- `search_symbols` — find symbols by name, kind, file, or namespace

## Links

- [GitHub](https://github.com/alexjsmith0115/synapse)
- [Changelog](https://github.com/alexjsmith0115/synapse/blob/main/CHANGELOG.md)
