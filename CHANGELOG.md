# Changelog

All notable changes to Synapps will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.4.0] - 2026-03-30

### Added
- **Pre-tool hooks for agent nudging** — gate scripts that remind AI agents (Claude Code, Cursor, Copilot) to query the Synapps graph before reading or editing files; installed via `synapps init`
- **`find_dead_code` MCP tool** *(experimental)* — find methods with zero callers, excluding tests, HTTP handlers, interface implementations, dispatch targets, constructors, and overrides
- **`find_tests_for` MCP tool** *(experimental)* — find which tests cover a given method via direct TESTS edge lookup
- **`find_untested` MCP tool** *(experimental)* — find production methods with no test coverage (same exclusions as `find_dead_code`)
- **`get_architecture` MCP tool** — single-call architecture overview returning packages, hotspots, HTTP endpoint map, and project stats
- **Import-based call resolution fallback** — tree-sitter-based `build_import_map` provides call resolution when the language server misses untyped symbols (TypeScript)
- **`@/` path alias resolution** — `tsconfig.json` path aliases (e.g., `@/*`) are resolved during TypeScript import mapping
- **Hook installer framework** — agent detector, per-agent config upsert/removal, gate script content constants, and force/skip logic
- **Shared vs dedicated database prompt** — `synapps init` now asks whether to use a shared or dedicated Memgraph instance
- **CI integration test job** — GitHub Actions workflow with Memgraph, .NET SDK, Node.js, and Java

### Changed
- **MCP tools consolidated from 21 to 15** — removed `get_symbol`, `get_symbol_source`, `find_callers`, `trace_call_chain`; merged `analyze_change_impact` into `get_context_for(scope='impact')` and `trace_http_dependency` into `find_http_endpoints(trace=True)`
- Removed standalone `synapps install` / `synapps uninstall` CLI commands — hooks are now offered during `synapps init`
- Removed CLI commands redundant with MCP tools
- Two-tone ASCII banner — SYN in dark green, APPS in light green
- Removed obsolete docs (demo, HTTP strategy, distribution, MCP consolidation)

### Fixed
- Strip JSONC comments from `tsconfig.json` before parsing path aliases
- `get_context_for` now resolves impact scope before symbol lookup
- `synapps init` auto-starts Memgraph instead of failing when the container is not running
- CI per-test timeout no longer bounds fixture setup (`timeout_func_only`)

## [1.3.0] - 2026-03-28

### Changed
- **Renamed project from Synapse to Synapps** — repository moved to SynappsCodeComprehension org
- Streamlined README from 777 to 449 lines
- Fixed HTTP client libraries table — added C#/Java, removed unsupported Python libs

## [1.2.0] - 2026-03-28

### Added
- **PyPI distribution** — install via `pip install synapps-mcp` (package renamed from `synapps` to `synapps-mcp`)
- **`synapps init` command** — interactive setup wizard that detects project languages, checks prerequisites, indexes the project, and configures MCP clients (Claude Desktop, Claude Code, Cursor, Copilot)
- **`__version__` attribute** — `synapps.__version__` returns the installed version at runtime via `importlib.metadata`
- **CI/CD publish workflow** — `.github/workflows/publish.yml` builds, smoke-tests, and publishes to PyPI on `v*` tags via OIDC trusted publishing
- **Wheel smoke test** — CI verifies `solidlsp` and all 4 tree-sitter grammars are included in the published wheel
- **Platform-aware doctor fix strings** — every failed check shows exact install commands for macOS (`brew`) or Linux (`apt-get`)
- **Actionable error messages** — Docker-not-running, Memgraph connection lost, project-not-indexed, and language server timeout errors all show recovery commands
- **MCP client auto-detection** — `synapps init` finds installed MCP clients and offers to write config with atomic merge (preserves existing server entries)

### Changed
- Package distribution name changed from `synapps` to `synapps-mcp` (Python import paths unchanged)
- `synapps doctor` now exits with code 1 when any check fails (enables use in scripts and CI)
- SYNAPPS logo banner moved from `synapps index` (first run) to `synapps init`
- Version bumped from 1.0.0 to 1.2.0

### Fixed
- Language server timeout no longer aborts the entire indexing pass — timed-out files are skipped with a warning naming the file

## [1.1.0] - 2026-03-28

### Added
- `find_http_endpoints` MCP tool — search endpoints by route pattern, HTTP method, or language
- `trace_http_dependency` MCP tool — find server handler and all client call sites for an endpoint
- Route conflict detection — indexer warns when multiple methods serve the same (HTTP method, route) pair
- JAX-RS annotation support (`@Path`, `@GET`, `@POST`, etc.) in Java server-side extraction
- README HTTP Endpoint Tracing section with supported frameworks table, tool examples, and known limitations

### Fixed
- Nested class HTTP call attribution now uses narrowest-range matching instead of last-match across all 4 extractors
- JAX-RS route constraints (`{param: regex}`) correctly normalized to `{param}` during extraction

### Changed
- HTTP endpoint extraction now runs by default — no longer requires `experimental.http_endpoints` config flag
- MCP tool count increased from 19 to 21
- Removed all "experimental" qualifiers from schema notes, agent instructions, and log messages

## [1.0.0] - 2026-03-26

### Added
- Multi-language indexing: C#, Python, TypeScript/JavaScript, Java
- Graph-based code intelligence via Memgraph
- MCP server with 25+ tools for AI agents
- CLI with full query and management capabilities
- Automatic per-project Docker container management
- Incremental sync via git diff
- Live file watching with `synapps watch`
- Interface dispatch resolution in call graph traversal
- Impact analysis with test coverage detection
- Token-efficient output format for AI consumption
- Scoped context retrieval (`structure`, `method`, `edit`)
- Architectural audit rules
- Symbol summaries (manual and auto-generated)
