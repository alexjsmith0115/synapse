# Changelog

All notable changes to Synapps will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **`synapps serve` CLI subcommand** — starts a local FastAPI web server at `http://127.0.0.1:7433` with configurable `--host`, `--port`, and `--open/--no-open` browser launch options
- **FastAPI web package** — new `synapps.web` package with `create_app(service)` factory returning a FastAPI app with `/api` route prefix, disabled docs UI, and conditional SPA static file serving
- **neo4j serialization utility** — `serialize_result()` in `synapps.web.serialization` converts neo4j `Node`/`Relationship` objects to plain dicts suitable for FastAPI JSON responses
- **`fastapi>=0.115.0` dependency** — added to project dependencies for the web UI backend
- **Localhost web UI — SPA scaffold** — new `spa/` directory at repo root with Svelte 5 + Vite build tooling; builds to `src/synapps/web/static/`; includes full CSS design system (green palette, light/dark themes), app shell layout (48px header, 240px sidebar, flex content area), dark mode toggle with `localStorage` persistence, and sidebar with 9 curated tools in 4 categories
- **REST API route modules** — 9 JSON endpoints across 4 route modules (`search`, `navigate`, `analysis`, `query`) wrapping curated `SynappsService` methods; `ValueError` from service returns HTTP 400; all results pass through `serialize_result()` for neo4j type safety; `execute_query` uses POST with Pydantic `CypherRequest` body validation
- **Localhost web UI — tool interaction layer** — API client (`api.js`) for all 9 tool endpoints; `toolConfig.js` with per-tool endpoint, method, params, and result type; `SymbolLink` component with clickable names and `vscode://file/` editor links; `DataTable` reusable table renderer; `ToolForm` dynamic parameter form per tool; `ResultPanel` adaptive renderer (table/text/mixed/graph/raw); graph data transforms (`calleesToElements`, `hierarchyToElements`, `cypherToElements`, `isGraphResult`) for Cytoscape; vitest unit tests for `toolConfig.js` and `transforms.js`
- **Cytoscape.js graph layer** — `spa/src/lib/graph/` module with `transforms.js` (API→Cytoscape element converters for callees, hierarchy, and Cypher results), `layouts.js` (dagre for call graphs/hierarchy, cose-bilkent for architecture/Cypher), `nodeStyles.js` (theme-aware green palette node colors per symbol kind via CSS custom properties), and `CytoscapeGraph.svelte` (interactive graph component with click-to-expand, double-click-to-editor, hover tooltip, zoom/pan, and MutationObserver-based theme switching)
- **Graph visualization wired into ResultPanel** — `ResultPanel` now renders `CytoscapeGraph` for `graph` resultType tools (`find_callees`, `get_hierarchy`) with accumulated graph state; clicking a node expands its callees and merges new nodes/edges into the visible graph (deduplicated by id); Cypher `raw` results auto-detect graph shape via `isGraphResult` and render interactively with a raw JSON toggle
- **SPA build script** — `scripts/build_spa.sh` runs `npm ci && npm run build` from the `spa/` directory for reproducible production builds
- **Static file serving test** — `tests/unit/web/test_static.py` verifies that API routes are not shadowed by the SPA static file catch-all, and that `index.html` is served when the static directory exists

### Fixed
- **SPA static file resolution** — `create_app()` now checks package dir, explicit override, and `CWD/src/synapps/web/static/` for the built SPA, fixing 404s when running via editable install or pipx
- **Analysis routes required path param** — `get_architecture`, `find_dead_code`, and `find_untested` web routes now accept `path` as optional (`str | None = None`) so the SPA can call them without a vestigial path parameter
- **Analysis routes missing subdirectory param** — all three analysis routes now accept an optional `subdirectory` query parameter for future directory-scoped analysis
- **find_usages web route returned markdown** — web route now passes `structured=True` to the service method, returning a JSON list of `{full_name, kind, file_path, line}` dicts suitable for graph rendering

### Changed
- **Unit test cleanup** — removed ~19 redundant, tautological, and brittle tests; merged duplicate doctor pass/fix assertions; replaced fragile Cypher brace-counting parser and exact-count schema assertions; renamed 5 misleading test names

## [1.5.1] - 2026-04-03

### Fixed
- **C#/TypeScript/Python indexing crash** — `CSharpTypeRefExtractor`, `TypeScriptTypeRefExtractor`, and `PythonTypeRefExtractor` now accept the `field_symbol_map` keyword argument added in 1.5.0 for Java field-level REFERENCES; previously indexing any non-Java project raised `TypeError: extract() got an unexpected keyword argument 'field_symbol_map'`

## [1.5.0] - 2026-04-03

### Added
- **Dead code exclusions for ASP.NET Core Startup/Program conventions** — `find_dead_code` and `find_untested` now exclude `Configure` and `ConfigureServices` in `Startup` and `Program` classes; `ConfigureWebHost`, `CreateHostBuilder`, and `CreateWebHostBuilder` are excluded by name; `Authorize`, `AllowAnonymous`, `GlobalSetup`, and `GlobalCleanup` attributes are excluded as framework entry points
- **External framework call stub recording** — new `ExternalCallStubber` class and `EXTERNAL_FRAMEWORK_METHODS` allowlist (8 types: RestTemplate, MongoTemplate, JdbcTemplate, KafkaTemplate, RabbitTemplate, ObjectMapper, WebClient, DiscoveryClient) create synthetic stub `Method` nodes so CALLS edges can be recorded for framework method invocations; stubs are excluded from dead code detection via a new `stub` property on `Method` nodes
- **End-to-end external framework call recording for Java** — `SymbolResolver` now accepts an `ExternalCallStubber` and invokes it at all unresolved call-site exit points; both full-index and file-reindex paths record `RestTemplate`, `MongoTemplate`, and other allowlisted framework calls as `CALLS` edges to synthetic stub nodes
- **`JavaCallExtractor` returns 5-tuples with receiver variable name** — `extract()` now returns `(caller, callee, line, col, receiver_name)` where `receiver_name` is the variable identifier before the dot for `receiver.method()` calls, or `None` for bare calls and constructors
- **Spring Data repository stub injection** — Spring Data interfaces (extending `CrudRepository`, `JpaRepository`, etc.) now get synthetic stub `Method` nodes for common CRUD operations (`save`, `findById`, `delete`, etc.), allowing CALLS edges from service classes to repository methods
- **Java field type extraction and `find_dependencies` fields section** — `JavaFieldTypeExtractor` extracts declared types from Java fields; `find_dependencies` now returns a `"fields"` section for classes with typed `Field` nodes (backward-compatible: classes without typed fields return a plain list)
- **`stub` field on `Method` nodes** — `upsert_method` now accepts a `stub=False` parameter; stub methods are written with `n.stub = true` in the graph and excluded from dead code queries via `coalesce(m.stub, false)`
- **Dead code `main(String[])` exclusion** — JDT LS stores Java main methods as `main(String[])` not `main`; `_build_base_exclusion_where` now handles both forms

### Fixed
- **Dead code false positives for Java `main()`, `configure()`, and `@Override`** — extended exclusion patterns for Spring Security adapters/configurers and Java `@Override` annotation
- **Dead code false positives for lifecycle methods** — `Dispose`, `DisposeAsync`, `Close`, `Finalize`, `OnNavigatedTo`, `OnInitialized`, and `OnInitializedAsync` excluded
- **C# null-conditional calls not indexed** — `obj?.Method()` patterns now produce CALLS edges
- **Mutation guard false positives in `execute_query`** — string literals and dotted property access stripped before keyword checking
- **Architecture stats accuracy** — Package and Endpoint nodes added to `total_symbols` count; HTTP client calls removed from architecture overview to reduce noise
- **Dead code pagination** — `find_dead_code` and `find_untested` use Python-level offset slicing instead of Cypher SKIP
- **C# generic IMPLEMENTS/INHERITS edges** — restored edges for generic C# types like `Repository<T>`

### Changed
- **`find_callees` and server instructions** — document known graph boundary: calls to external framework types are not indexed; agents should use `get_context_for` for framework call sites

## [1.4.14] - 2026-04-02

### Added
- **Indexing opt-out in init wizard** — users can skip Memgraph startup and indexing during `synapps init` while still persisting DB mode config
- **Unified agent configuration** — init wizard now presents a single multi-select for all AI harnesses (Claude Code, Cursor, Copilot, etc.) with auto-detected ones pre-checked
- **Java call resolution diagnostics** — `_resolve_file` now logs skipped call/type-ref counts on failure and emits a resolution summary when >30% of calls are unresolved

### Fixed
- **Init wizard language filter bug** — `smart_index` now respects `allowed_languages` parameter; previously all detected languages were indexed regardless of user selection
- **`SynappsService.smart_index` facade** — `allowed_languages` parameter is now forwarded through the service facade (was silently dropped, causing the wizard's language filter to be unreachable)
- **`get_context_for` TypeError regression** — `suggest_similar_names` query now guards against `None` `full_name` values; returns clean "Symbol not found" instead of raw TypeError
- **Dead code inflation** — `_FRAMEWORK_ATTRIBUTES` now includes lowercase Java Spring/JPA annotations (`@bean`, `@getmapping`, etc.) matching `JavaAttributeExtractor`'s `.lower()` storage
- **Architecture hotspots skewed by vendored JS** — `_VENDORED_PATH_PATTERN` extended to match `static/js/` directories and named CDN library files (angular.js, vue.js, jquery.js, etc.)
- **Duplicate package names in `get_architecture`** — package query now returns `p.full_name` instead of `p.name` for fully-qualified package names
- **Package `file_count: 0` in `get_architecture`** — replaced unreliable `STARTS WITH` string matching with `CONTAINS` edge traversal for accurate file counts

## [1.4.13] - 2026-04-01

### Added
- **C# ASP.NET Core Minimal API endpoint detection** — `MapGet`, `MapPost`, `MapPut`, `MapDelete`, and `MapPatch` calls now produce HTTP_ENDPOINT nodes in the graph
- **`RestTemplate.exchange()` detection** — Java HTTP extractor now recognizes `RestTemplate.exchange()` calls with `HttpMethod.X` verb arguments
- **MSTest attribute support** — `[TestMethod]` and `[DataTestMethod]` attributes now produce TESTS edges

### Fixed
- **7 Java tool issues** — import routing, `_clean_java_full_name`, per-file source root detection, anonymous class filter, `kind=4` NAMESPACE mapping, and accurate line numbers via `selectionRange.start.line`
- **`scope=edit` empty-state visibility** — `get_context_for` with `scope=edit` now shows a clearer message when no callers/callees exist
- **HTTP endpoint section in `get_context_for`** — edit scope now includes HTTP endpoints associated with the symbol
- **Result limits** — `find_dead_code` and `find_untested` now accept a `limit` parameter to cap output size
- **`_get_service` singleton invalidation** — CLI service cache now invalidates when the target project path changes
- **`Repository.name`** — `upsert_repository` now derives `Repository.name` from `os.path.basename(path)` instead of storing the full path

## [1.4.12] - 2026-04-01

### Added
- **Java package extraction** — package declarations are now extracted via tree-sitter and wired as Package CONTAINS edges in the graph

### Fixed
- **NUnit attribute support** — `[Test]` and `[TestCase]` attributes now produce TESTS edges (previously only `[Fact]`/`[Theory]` from xUnit were recognized)
- **Java method attribute lookup** — parameter signatures are now stripped before matching attribute names, fixing false negatives on annotated methods

## [1.4.11] - 2026-03-31

### Fixed
- **Cursor MCP config detection** — `synapps init` no longer requires `.cursor/` directory to pre-exist; the directory is created if needed

## [1.4.10] - 2026-03-31

### Added
- **Agent instruction file installation** — `synapps init` now installs agent instruction files (CLAUDE.md, AGENTS.md, GEMINI.md, etc.) into projects for immediate AI agent context

## [1.4.8] - 2026-03-31

### Fixed
- **`find_usages` parameter cleanup** — removed misleading `include_test_breakdown` parameter that was accepted but silently ignored

## [1.4.7] - 2026-03-31

### Added
- **Version display** — `synapps status` CLI command and `list_projects` MCP tool now include the Synapps version in their output
- **Cross-language integration tests** — 30+ new integration tests ensuring MCP and CLI tool parity across all 4 language suites (C#, Python, TypeScript, Java)

## [1.4.6] - 2026-03-31

### Fixed
- **DISPATCHES_TO callers included in caller lookups** — `find_callers` and `find_callers_with_sites` now include callers that reach a method via interface dispatch (DISPATCHES_TO edges), which were previously excluded

## [1.4.5] - 2026-03-31

### Fixed
- **C# generic method call extraction** — generic invocations like `_service.Method<T>()` and `new List<string>()` now correctly produce CALLS edges; previously the `generic_name` AST node in `invocation_expression` and `object_creation_expression` was not matched by the tree-sitter query, silently dropping all generic method calls from the graph

## [1.4.4] - 2026-03-30

### Fixed
- **Cross-file edges preserved during incremental reindex** — `reindex_file` no longer drops CALLS and DISPATCHES_TO edges to symbols defined in other files

## [1.4.3] - 2026-03-30

### Fixed
- **Declaring-type lookup scoped to current file** — `_index_base_types()` now restricts declaring-type resolution to the current file, preventing cross-file false-positive base type matches

## [1.4.2] - 2026-03-30

### Changed
- **LSP-based base type resolution** — `_index_base_types()` now uses Language Server Protocol for base type resolution instead of namespace disambiguation; all 4 language extractors return 5-tuples with position data; dead namespace disambiguation functions removed

## [1.4.1] - 2026-03-30

### Fixed
- **C# generic HTTP method extraction** — `GetFromJsonAsync<T>`, `PostAsJsonAsync<T>`, and other generic `System.Net.Http.Json` methods now correctly produce HTTP_CALLS edges; previously the `generic_name` AST node caused the method name to be missed
- **False-positive IMPLEMENTS edges across projects** — structural protocol dispatch (matching classes to interfaces by method names) is now restricted to Python only; C#, Java, and TypeScript use nominal typing where IMPLEMENTS edges come from LSP declarations
- **Cursor hooks installed at user-level instead of project-level** — `synapps init` now writes Cursor hooks to `<project>/.cursor/hooks.json` instead of `~/.cursor/hooks.json`

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
