# Changelog

All notable changes to Synapse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.2.0] - 2026-03-28

### Added
- **PyPI distribution** — install via `pip install synapse-mcp` (package renamed from `synapse` to `synapse-mcp`)
- **`synapse init` command** — interactive setup wizard that detects project languages, checks prerequisites, indexes the project, and configures MCP clients (Claude Desktop, Claude Code, Cursor, Copilot)
- **`__version__` attribute** — `synapse.__version__` returns the installed version at runtime via `importlib.metadata`
- **CI/CD publish workflow** — `.github/workflows/publish.yml` builds, smoke-tests, and publishes to PyPI on `v*` tags via OIDC trusted publishing
- **Wheel smoke test** — CI verifies `solidlsp` and all 4 tree-sitter grammars are included in the published wheel
- **Platform-aware doctor fix strings** — every failed check shows exact install commands for macOS (`brew`) or Linux (`apt-get`)
- **Actionable error messages** — Docker-not-running, Memgraph connection lost, project-not-indexed, and language server timeout errors all show recovery commands
- **MCP client auto-detection** — `synapse init` finds installed MCP clients and offers to write config with atomic merge (preserves existing server entries)

### Changed
- Package distribution name changed from `synapse` to `synapse-mcp` (Python import paths unchanged)
- `synapse doctor` now exits with code 1 when any check fails (enables use in scripts and CI)
- SYNAPSE logo banner moved from `synapse index` (first run) to `synapse init`
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
- Live file watching with `synapse watch`
- Interface dispatch resolution in call graph traversal
- Impact analysis with test coverage detection
- Token-efficient output format for AI consumption
- Scoped context retrieval (`structure`, `method`, `edit`)
- Architectural audit rules
- Symbol summaries (manual and auto-generated)
