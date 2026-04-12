*IMPORTANT*
- Never assume the user is correct. Trust but verify all statements, using the code as a source of truth. When in doubt, ask the user for clarification.
- Design all classes and functions with testability in mind. Use Dependency Injection liberally.
- Keep classes and functions small, clear, and with a singular purpose (SRP).
- Use comments sparingly. Comments should only exist to clarify a design choice/decision, not to explain what the code is doing. (WHY not WHAT)
- Make sure all unit and integration tests pass before considering a task complete.
- Every bugfix must include a regression test that would have caught the bug.

## Common Commands

```bash
# Activate venv (always required before running Python commands)
source .venv/bin/activate

# Unit tests (no external dependencies, ~1.7s)
pytest tests/unit/ -v

# Integration tests (requires Memgraph on localhost:7687 and .NET SDK)
docker compose up -d  # start Memgraph + Memgraph Lab (Lab UI at http://localhost:3000; in-memory — data lost on restart, tests always re-index from scratch)
pytest tests/integration/test_mcp_tools.py -v -m integration      # MCP tool integration(C#) tests
pytest tests/integration/test_mcp_tools_typescript.py -v -m integration # Typescript integration tests (MCP)
pytest tests/integration/test_mcp_tools_python.py -v -m integration # Python integration tests (MCP)

pytest tests/integration/test_cli_commands.py -v -m integration   # CLI command integration tests
pytest tests/integration/test_cli_commands_python.py -v -m integration   # Python CLI command integration tests
pytest tests/integration/test_cli_commands_typescript.py -v -m integration   # typescript CLI command integration tests
```

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Synapps**

Synapps is a code intelligence MCP server that indexes multi-language codebases (C#, TypeScript, Python, Java) using tree-sitter and Language Server Protocol, stores symbols and relationships in a Memgraph graph database, and exposes semantic query tools (find callers, trace call chains, analyze change impact) for AI coding agents and developers via both MCP and CLI.

**Core Value:** AI coding agents can instantly understand code structure and relationships across an entire codebase without reading every file.

### Constraints

- **Tech stack**: Python 3.11, existing CLI (typer), existing MCP server (FastMCP) — new features must integrate with these
- **No auto-install**: Report + instructions only — users stay in control of their environment
- **Platform**: Must work on macOS and Linux at minimum (Docker required for Memgraph)
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages & Runtime
- **Python 3.11** — entire application codebase (`src/synapps/`, `src/solidlsp/`)
- **Cypher** — graph query language used in all `GraphConnection` calls (`src/synapps/graph/`)
- **C#, TypeScript, Python, Java** — target languages indexed by the tool (not part of the tool's own runtime)
## Frameworks & Libraries
| Library | Version | Purpose | Location |
|---------|---------|---------|----------|
| `mcp` | >=1.0.0 (installed: 1.26.0) | Model Context Protocol SDK — exposes the MCP server | `src/synapps/mcp/server.py` |
| `neo4j` | >=5.0.0 (installed: 6.1.0) | Bolt-protocol driver used against Memgraph | `src/synapps/graph/connection.py` |
| `typer` | >=0.12.0 (installed: 0.24.1) | CLI framework for the `synapps` command | `src/synapps/cli/app.py` |
| `watchdog` | >=4.0.0 (installed: 6.0.0) | Filesystem event watcher for live re-indexing | `src/synapps/watcher/watcher.py` |
| `pydantic` | >=2.0.0 | Data validation (declared; minimal direct usage observed) | `pyproject.toml` |
| `sensai-utils` | >=1.5.0 (installed: 1.6.0) | Pickle cache, string mixins, logging utilities | `src/solidlsp/ls.py`, `src/solidlsp/ls_process.py`, `src/synapps/util/file_system.py` |
| `overrides` | >=7.7.0 | Runtime enforcement of `@override` decorator | `src/solidlsp/` |
| `pathspec` | >=0.12.1 | `.gitignore`-style path matching for ignored paths | `src/synapps/util/file_system.py` |
| `psutil` | >=7.0.0 | Process management for language server subprocesses | `pyproject.toml` |
| `beautifulsoup4` | >=4.12.0 | HTML parsing in text utilities | `src/synapps/util/text_utils.py` |
| `joblib` | >=1.3.0 | Parallel execution for batch indexing operations | `src/synapps/util/text_utils.py` |
| `charset-normalizer` | >=3.0.0 | File encoding detection | `pyproject.toml` |
| `requests` | >=2.31.0 | HTTP calls (e.g., language server binary downloads) | `pyproject.toml` |
| `tree-sitter` | >=0.24.0 | Core parsing engine for AST extraction | `src/synapps/indexer/tree_sitter_util.py`, all language plugin indexers |
| `tree-sitter-c-sharp` | >=0.23.0 | C# grammar for tree-sitter | `src/synapps/indexer/indexer.py`, `src/synapps/plugin/csharp.py` |
| `tree-sitter-python` | >=0.25.0 | Python grammar for tree-sitter | `src/synapps/plugin/python.py`, `src/synapps/indexer/python/` |
| `tree-sitter-typescript` | >=0.23.2 | TypeScript/JavaScript grammar for tree-sitter | `src/synapps/plugin/typescript.py`, `src/synapps/indexer/typescript/` |
| `tree-sitter-java` | >=0.23.0 | Java grammar for tree-sitter | `src/synapps/plugin/java.py` |
| `docker` | >=7.0.0 | Docker SDK — manages per-project Memgraph containers | `src/synapps/container/manager.py` |
| `pyright` | >=1.1.0 | Python language server (bundled binary, used by solidlsp) | `src/solidlsp/language_servers/pyright_server.py` |
| Library | Version | Purpose |
|---------|---------|---------|
| `pytest` | >=8.0.0 | Test runner |
| `pytest-timeout` | >=2.0.0 | Per-test timeouts (default 10s via `pytest.ini`) |
## Key Dependencies
## Configuration
| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, all runtime dependencies, dev dependencies, build targets, CLI entry points |
| `pytest.ini` | Test runner config — 10s timeout, `tests/` path, `src tests/unit` on `pythonpath`, `integration` marker |
| `docker-compose.yml` | Development convenience — starts a shared Memgraph instance on `localhost:7687` and Memgraph Lab UI on `localhost:3000` |
| `.synapps/config.json` | Per-project runtime config (created on first run, not checked in) — stores container name and allocated Bolt port |
| `uv.lock` | Full dependency lockfile |
| Variable | Purpose |
|----------|---------|
| `SYNAPPS_BENCH_LOG` | Optional path to a JSONL file for tool call benchmarking (`src/synapps/mcp/tools.py`) |
## Build & Dev Tools
- `synapps` → `synapps.cli:app` (Typer app, `src/synapps/cli/app.py`)
- `synapps-mcp` → `synapps.mcp.server:main` (MCP server, `src/synapps/mcp/server.py`)
- `csharp-ls` (Microsoft) — C# indexing
- `typescript-language-server` + `tsserver` — TypeScript/JavaScript
- Eclipse JDT LS — Java
- OmniSharp — alternative C# (experimental)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Style & Formatting
- **Indentation:** 4 spaces (Python standard)
- **Quotes:** Double quotes for strings; single quotes appear occasionally but doubles dominate
- **Line length:** Not formally enforced (no ruff/black/isort config detected in `pyproject.toml`)
- **Trailing commas:** Used in multi-line argument lists and collections
- **`from __future__ import annotations`:** Present in virtually every source file — enables PEP 604 union syntax (`X | Y`) across the entire codebase regardless of Python version
- **Type hints:** Consistently applied to all function signatures; return types always annotated
- **No linter config detected:** No `[tool.ruff]`, `[tool.mypy]`, `[tool.black]`, or `.ruff.toml` present. Conventions are maintained by code review, not tooling.
## Naming Conventions
| Element | Convention | Example |
|---------|-----------|---------|
| Classes | PascalCase | `SynappsService`, `GraphConnection`, `PythonCallExtractor` |
| Functions (module-level) | snake_case | `upsert_repository`, `compute_sync_diff` |
| Methods | snake_case | `get_workspace_files`, `index_project` |
| Private methods/functions | `_snake_case` prefix | `_get_project_roots`, `_rel_path`, `_resolve` |
| Private module helpers | `_snake_case` prefix | `_p`, `_slim`, `_apply_limit`, `_short_ref` |
| Constants / module-level literals | `_UPPER_SNAKE` (private) | `_ALWAYS_SKIP`, `_MINIFIED_LINE_THRESHOLD`, `_PYTHON_CALLS_QUERY` |
| Variables | snake_case | `root_path`, `symbol_map`, `file_extensions` |
| Type aliases / Literals | PascalCase or `CamelCaseLiteral` | `SymbolKindLiteral`, `AuditRuleLiteral` |
| Dataclass fields | snake_case | `updated`, `deleted`, `unchanged` |
| Logger | always named `log` at module level | `log = logging.getLogger(__name__)` |
| Language-specific extractors | `{Language}{Concept}Extractor` | `PythonCallExtractor`, `CSharpBaseTypeExtractor` |
| LSP adapters | `{Language}LSPAdapter` | `PythonLSPAdapter`, `TypeScriptLSPAdapter` |
| Plugin classes | `{Language}Plugin` | `PythonPlugin`, `CSharpPlugin`, `JavaPlugin` |
## Common Patterns
## Error Handling
## Imports & Dependencies
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Overview
## Pattern
```
```
- `ContainerManager` manages a per-project Memgraph Docker container
- `FileWatcher` provides live re-indexing via filesystem events
- `LanguageRegistry` + `LanguagePlugin` protocol enables multi-language support
## Layers & Components
- Purpose: Accept user commands or AI agent tool calls; delegate to `SynappsService`
- Location: `src/synapps/cli/app.py`, `src/synapps/mcp/server.py`
- Depends on: `SynappsService`, `ContainerManager`, `graph.schema`
- Purpose: Single orchestration point for all indexing, syncing, querying, and watching operations
- Location: `src/synapps/service.py`
- Holds: `GraphConnection`, `LanguageRegistry`, active `FileWatcher` instances
- Depends on: `graph.*`, `indexer.*`, `lsp.*`, `plugin.*`, `watcher.*`
- Purpose: Provision and manage per-project Memgraph containers via Docker; persist port assignments in `.synapps/config.json`
- Location: `src/synapps/container/manager.py`
- Provides: `GraphConnection` to the rest of the system
- Purpose: Walk project files, extract symbols via `LSPAdapter`, write nodes/edges to graph
- Location: `src/synapps/indexer/`
- Sub-components:
- Purpose: Decouple language-specific extraction from the indexer core; each language provides factory methods for LSP adapter, call extractor, import extractor, type-ref extractor, and attribute extractor
- Location: `src/synapps/plugin/` (one module per language: `csharp.py`, `python.py`, `typescript.py`, `java.py`)
- Protocol: `LanguagePlugin` (structural protocol, runtime-checkable) at `src/synapps/plugin/__init__.py`
- Registry: `LanguageRegistry` in the same file; `default_registry()` registers all four built-in plugins
- Purpose: Bridge between language server output and the `IndexSymbol` / `LSPAdapter` interface that the indexer consumes
- Location: `src/synapps/lsp/` — one adapter per language (`csharp.py`, `python.py`, `typescript.py`, `java.py`)
- Interface: `LSPAdapter` protocol and `IndexSymbol` dataclass at `src/synapps/lsp/interface.py`
- Backend: Adapters delegate to `solidlsp` (the bundled LSP process manager)
- Purpose: Launch, manage, and communicate with external language server processes over the LSP protocol (JSON-RPC stdio)
- Location: `src/solidlsp/`
- Key files: `ls.py` (base `LanguageServer` ABC), `ls_process.py` (process lifecycle), `lsp_protocol_handler/` (JSON-RPC transport)
- Language servers: `language_servers/csharp_language_server.py`, `language_servers/pyright_server.py`, `language_servers/typescript_language_server.py`, `language_servers/eclipse_jdtls.py`
- Purpose: All Cypher query logic; no business logic lives here — pure data access
- Location: `src/synapps/graph/`
- Purpose: Expose graph queries as MCP tools callable by AI agents; thin wrappers over `SynappsService`
- Location: `src/synapps/mcp/tools.py`, `src/synapps/mcp/server.py`, `src/synapps/mcp/instructions.py`
- Purpose: Watch a project directory for file changes and trigger re-indexing via callback
- Location: `src/synapps/watcher/watcher.py`
- Uses: `watchdog` library; debounce logic for rapid file saves
## Data Flow
- Persistent graph state lives in Memgraph (in-memory per container restart unless using persistent storage)
- Per-project config (port, container name) is persisted in `.synapps/config.json`
- Indexed commit SHA is stored on the `Repository` node in the graph
## Entry Points
| Entry Point | Type | Location |
|-------------|------|----------|
| `synapps` CLI | CLI (Typer) | `src/synapps/cli/app.py` |
| `synapps-mcp` MCP server | MCP (stdio) | `src/synapps/mcp/server.py` |
## Key Abstractions
- Structural protocol (`@runtime_checkable`) defining the contract for each language
- Methods: `create_lsp_adapter()`, `create_call_extractor()`, `create_import_extractor()`, `create_base_type_extractor()`, `create_attribute_extractor()`, `create_type_ref_extractor()`, `create_assignment_extractor()`, `parse_file()`
- Location: `src/synapps/plugin/__init__.py`
- Implementations: `src/synapps/plugin/csharp.py`, `python.py`, `typescript.py`, `java.py`
- Interface between language server output and the indexer
- Methods: `get_workspace_files()`, `get_document_symbols()`, `find_method_calls()`, `find_overridden_method()`
- Location: `src/synapps/lsp/interface.py`
- Implementations: `src/synapps/lsp/csharp.py`, `python.py`, `typescript.py`, `java.py`
- Canonical in-memory representation of a symbol extracted from source
- Fields: `name`, `full_name`, `kind`, `file_path`, `line`, `end_line`, `signature`, `base_types`, `parent_full_name`
- Location: `src/synapps/lsp/interface.py`
- Wraps a `neo4j.Driver` pointed at Memgraph via Bolt
- Methods: `query()`, `execute()`, `execute_implicit()`, `query_with_timeout()`
- Location: `src/synapps/graph/connection.py`
- Facade that owns the `GraphConnection` and `LanguageRegistry`; all public operations go through it
- Location: `src/synapps/service.py`
- Nodes: `Repository`, `Directory`, `File`, `Package`, `Class`, `Interface`, `Method`, `Property`, `Field`
- Edges: `CONTAINS`, `INHERITS`, `IMPLEMENTS`, `DISPATCHES_TO`, `CALLS`, `REFERENCES`, `OVERRIDES`, `IMPORTS`
- `DISPATCHES_TO` is the traversal-friendly inverse of method-level `IMPLEMENTS`, written at index time to allow interface-crossing path queries without mixed-direction variable-length patterns
## Error Handling
- `SynappsService._resolve()` raises `ValueError` for ambiguous short names with a list of candidates
- `ContainerManager.get_connection()` raises `RuntimeError` if Docker is not available
- `ContainerManager._wait_for_bolt()` raises `TimeoutError` if Memgraph does not become ready within 30s
- `GraphConnection.query_with_timeout()` raises `TimeoutError` with a user-friendly message after configurable timeout
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->

<!-- synapps:start -->
## Synapps MCP

This project is indexed by the **Synapps** code-intelligence graph.
Use Synapps MCP tools instead of grep or file reads for understanding code structure, relationships, and navigating symbols.

### Workflow
- Projects must be indexed before querying. Call `list_projects` to check what is indexed, `index_project` to index a new project, `sync_project` to refresh a stale index.
- If queries return empty results, call `list_projects(path=...)` to check whether the project is indexed.

### Primary tools (start here)
| Task | Tool | Instead of |
|------|------|------------|
| Read source code of a symbol | `read_symbol` | cat/head/tail file reads |
| Understand a symbol before editing | `get_context_for` | manual file reads |
| Find a symbol by name | `search_symbols` | grep for symbol name |
| Find who calls a method | `find_usages` | grep for method name |

### Secondary tools
| Task | Tool | Instead of |
|------|------|------------|
| Impact analysis before changes | `assess_impact` | manual caller tracing |
| Type member overview without source | `get_context_for` with members_only=True | — |
| Find what a method calls | `find_callees` (use `depth` for reachable call tree) | `execute_query` |
| All usages of any symbol | `find_usages` (use `kind` to filter type refs) | grep |
| Find all implementations of an interface | `find_implementations` | — |
| Architecture overview | `get_architecture` | — |
| Custom graph queries | `get_schema` then `execute_query` (last resort) | — |

### Avoid
- Do not use `execute_query` when a dedicated tool exists for the task.
- Do not read files with grep or cat when `read_symbol` or `get_context_for` can retrieve the exact code.
- Do not guess symbol names — use `search_symbols` to discover them first.
- Before modifying a method, use `get_context_for` to understand context and `assess_impact` to check callers and tests.
<!-- synapps:end -->
